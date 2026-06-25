from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import struct
import time
from urllib.parse import quote


TOTP_ISSUER = "JurisDigta"
TOTP_DIGITS = 6
TOTP_INTERVAL_SECONDS = 30


def generate_totp_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def totp_provisioning_uri(*, secret: str, email: str, issuer: str = TOTP_ISSUER) -> str:
    label = f"{issuer}:{email.strip().lower()}"
    return (
        f"otpauth://totp/{quote(label)}?"
        f"secret={quote(secret)}&issuer={quote(issuer)}&algorithm=SHA1&digits={TOTP_DIGITS}"
        f"&period={TOTP_INTERVAL_SECONDS}"
    )


def verify_totp_code(*, secret: str, code: str, at_time: int | None = None, window: int = 1) -> bool:
    normalized_code = "".join(ch for ch in code.strip() if ch.isdigit())
    if len(normalized_code) != TOTP_DIGITS:
        return False
    timestamp = int(time.time() if at_time is None else at_time)
    counter = timestamp // TOTP_INTERVAL_SECONDS
    for offset in range(-window, window + 1):
        expected = _totp_at_counter(secret=secret, counter=counter + offset)
        if hmac.compare_digest(expected, normalized_code):
            return True
    return False


def current_totp_code(*, secret: str, at_time: int | None = None) -> str:
    timestamp = int(time.time() if at_time is None else at_time)
    return _totp_at_counter(secret=secret, counter=timestamp // TOTP_INTERVAL_SECONDS)


def protect_totp_secret(secret: str) -> str:
    key = _totp_encryption_key()
    nonce = secrets.token_bytes(16)
    plaintext = secret.encode("utf-8")
    ciphertext = _xor_bytes(plaintext, _keystream(key=key, nonce=nonce, length=len(plaintext)))
    tag = hmac.new(key, nonce + ciphertext, hashlib.sha256).digest()
    return "v1:" + base64.urlsafe_b64encode(nonce + tag + ciphertext).decode("ascii")


def reveal_totp_secret(protected_secret: str) -> str | None:
    if not protected_secret.startswith("v1:"):
        return None
    try:
        payload = base64.urlsafe_b64decode(protected_secret[3:].encode("ascii"))
    except Exception:
        return None
    if len(payload) < 49:
        return None
    nonce = payload[:16]
    tag = payload[16:48]
    ciphertext = payload[48:]
    key = _totp_encryption_key()
    expected_tag = hmac.new(key, nonce + ciphertext, hashlib.sha256).digest()
    if not hmac.compare_digest(tag, expected_tag):
        return None
    plaintext = _xor_bytes(ciphertext, _keystream(key=key, nonce=nonce, length=len(ciphertext)))
    return plaintext.decode("utf-8")


def _totp_at_counter(*, secret: str, counter: int) -> str:
    key = _decode_base32_secret(secret)
    message = struct.pack(">Q", counter)
    digest = hmac.new(key, message, hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(value % (10**TOTP_DIGITS)).zfill(TOTP_DIGITS)


def _decode_base32_secret(secret: str) -> bytes:
    normalized = "".join(secret.strip().upper().split())
    padding = "=" * ((8 - len(normalized) % 8) % 8)
    return base64.b32decode(normalized + padding)


def _totp_encryption_key() -> bytes:
    raw = (
        os.getenv("TOTP_SECRET_ENCRYPTION_KEY", "").strip()
        or os.getenv("MCP_API_JWT_SECRET", "").strip()
        or os.getenv("JWT_SECRET", "").strip()
        or "local-jurisdigta-totp-development-key"
    )
    return hashlib.sha256(raw.encode("utf-8")).digest()


def _keystream(*, key: bytes, nonce: bytes, length: int) -> bytes:
    output = bytearray()
    block = 0
    while len(output) < length:
        output.extend(hmac.new(key, nonce + block.to_bytes(4, "big"), hashlib.sha256).digest())
        block += 1
    return bytes(output[:length])


def _xor_bytes(left: bytes, right: bytes) -> bytes:
    return bytes(a ^ b for a, b in zip(left, right))
