"""Versioned platform-managed case encryption. Never logs keys or payloads."""
from __future__ import annotations

import base64
import json
import hashlib
import threading
import time
from collections import OrderedDict
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

if TYPE_CHECKING:
    from .api_db import ApiDatabaseStore

PREFIX = "jdenc1:"


class CaseEncryptionError(RuntimeError):
    """Safe diagnostic; intentionally excludes ciphertext and underlying errors."""


class CaseCipher:
    def __init__(self, store: ApiDatabaseStore, key_file: str) -> None:
        self.store = store
        self.key_file = key_file
        self._cache: OrderedDict[str, tuple[float, str, bytes]] = OrderedDict()
        self._lock = threading.Lock()

    def _ring(self) -> tuple[str, dict[str, bytes]]:
        try:
            data = json.loads(Path(self.key_file).read_text(encoding="utf-8-sig"))
            keys = {str(k): base64.b64decode(v, validate=True) for k, v in data["keys"].items()}
            active = str(data["active"])
            if active not in keys or any(len(key) != 32 for key in keys.values()):
                raise ValueError()
            return active, keys
        except Exception:
            raise CaseEncryptionError("Case encryption key unavailable") from None

    def key(self, case_id: str, *, create: bool = False) -> bytes:
        active, ring = self._ring()
        fingerprint = hashlib.sha256(b"".join(k.encode() + v for k, v in sorted(ring.items()))).hexdigest()
        with self._lock:
            cached = self._cache.get(case_id)
            if cached and cached[0] > time.monotonic() and cached[1] == fingerprint:
                self._cache.move_to_end(case_id)
                return cached[2]
        with self.store._connect() as conn:
            row = self.store._fetchone(conn, "SELECT key_id, wrapped_key FROM case_encryption_keys WHERE case_id = ?", (case_id,))
            if row is None and create:
                erased = self.store._fetchone(conn, "SELECT 1 FROM case_encryption_erased WHERE case_id = ?", (case_id,))
                if erased:
                    raise CaseEncryptionError("Case encryption key was erased")
                dek = AESGCM.generate_key(bit_length=256)
                nonce = os.urandom(12)
                wrapped = base64.b64encode(nonce + AESGCM(ring[active]).encrypt(nonce, dek, case_id.encode())).decode()
                self.store._execute(conn, "INSERT INTO case_encryption_keys(case_id, key_id, wrapped_key) VALUES (?, ?, ?) ON CONFLICT(case_id) DO NOTHING", (case_id, active, wrapped))
                row = self.store._fetchone(conn, "SELECT key_id, wrapped_key FROM case_encryption_keys WHERE case_id = ?", (case_id,))
        try:
            if row is None:
                raise ValueError()
            blob = base64.b64decode(row[1], validate=True)
            dek = AESGCM(ring[str(row[0])]).decrypt(blob[:12], blob[12:], case_id.encode())
            with self._lock:
                self._cache[case_id] = (time.monotonic() + 15, fingerprint, dek)
                while len(self._cache) > 128:
                    self._cache.popitem(last=False)
            return dek
        except Exception:
            raise CaseEncryptionError("Case key unavailable or invalid") from None

    def encrypt(self, case_id: str, purpose: str, payload: bytes) -> str:
        nonce = os.urandom(12)
        aad = json.dumps([case_id, purpose], separators=(",", ":")).encode()
        encrypted = AESGCM(self.key(case_id, create=True)).encrypt(nonce, payload, aad)
        return PREFIX + base64.b64encode(nonce + encrypted).decode()

    def decrypt(self, case_id: str, purpose: str, value: str) -> bytes:
        return self.decrypt_many(case_id, [(purpose, value)])[0]

    def decrypt_many(self, case_id: str, values: list[tuple[str, str]]) -> list[bytes]:
        """Resolve the case key once per authorized retrieval batch, not per chunk."""
        if not values:
            return []
        if any(not value.startswith(PREFIX) for _, value in values):
            raise CaseEncryptionError("Legacy plaintext requires migration")
        try:
            cipher = AESGCM(self.key(case_id))
            result = []
            for purpose, value in values:
                blob = base64.b64decode(value[len(PREFIX):], validate=True)
                aad = json.dumps([case_id, purpose], separators=(",", ":")).encode()
                result.append(cipher.decrypt(blob[:12], blob[12:], aad))
            return result
        except Exception:
            raise CaseEncryptionError("Encrypted case data unavailable or invalid") from None

    def rotate(self, case_id: str) -> None:
        with self._lock:
            self._cache.pop(case_id, None)
        dek = self.key(case_id)
        active, ring = self._ring()
        nonce = os.urandom(12)
        wrapped = base64.b64encode(nonce + AESGCM(ring[active]).encrypt(nonce, dek, case_id.encode())).decode()
        with self.store._connect() as conn:
            self.store._execute(conn, "UPDATE case_encryption_keys SET key_id = ?, wrapped_key = ? WHERE case_id = ?", (active, wrapped, case_id))


def initialize_case_security(store: ApiDatabaseStore) -> None:
    script = (Path(__file__).resolve().parents[2] / "databases/api/migrations/0922_case_security.sql").read_text()
    with store._connect() as conn:
        store._execute_script(conn, script)


def decrypt_fields(store: ApiDatabaseStore, row: tuple[Any, ...], case_index: int, fields: dict[int, str]) -> tuple[Any, ...]:
    values = list(row)
    for index, purpose in fields.items():
        if index < len(values) and values[index] is not None:
            values[index] = store.decrypt_case_text(str(values[case_index]), purpose, str(values[index]))
    return tuple(values)
