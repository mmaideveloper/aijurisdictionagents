from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import time
from collections.abc import Callable
from typing import Any

import httpx

from .domain import CourtDecisionRecord
from .pseudonymization import pseudonymize_court_decision_text

ProgressLogger = Callable[[str], None]
SleepFunction = Callable[[float], None]


@dataclass(frozen=True)
class InfoSudDecisionRef:
    guid: str
    label: str


@dataclass(frozen=True)
class InfoSudDecisionPage:
    refs: tuple[InfoSudDecisionRef, ...]
    page: int
    size: int
    total: int
    source_updated_at: str = ""


class InfoSudSourceClient:
    source_system = "infosud"

    def __init__(
        self,
        *,
        base_url: str,
        timeout_seconds: float = 90.0,
        retry_attempts: int = 3,
        retry_backoff_seconds: float = 5.0,
        tls_verify: bool = True,
        progress_logger: ProgressLogger | None = None,
        sleep_fn: SleepFunction = time.sleep,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.retry_attempts = retry_attempts
        self.retry_backoff_seconds = retry_backoff_seconds
        self.tls_verify = tls_verify
        self.progress_logger = progress_logger or (lambda _message: None)
        self.sleep_fn = sleep_fn

    def list_decisions(self, *, page: int = 0, size: int = 25) -> list[InfoSudDecisionRef]:
        return list(self.list_decision_page(page=page, size=size).refs)

    def list_decision_page(self, *, page: int = 0, size: int = 25) -> InfoSudDecisionPage:
        """Return a zero-based page plus the source corpus size.

        InfoSud's public API is one-based even though its response reports a
        zero-based page.  Keeping that translation here prevents the worker
        from requesting the first page twice.
        """
        if page < 0:
            raise ValueError("page must be >= 0")
        payload = self._get_json(
            path="/rozhodnutie",
            params={"page": page + 1, "size": size},
            context=f"stage=list_decision_page page={page} size={size}",
        )
        return InfoSudDecisionPage(
            refs=_refs_from_payload(payload),
            page=page,
            size=size,
            total=_non_negative_int(payload.get("numFound")),
            source_updated_at=_first_text(payload, "updateDate"),
        )

    def get_decision(self, guid: str) -> CourtDecisionRecord:
        payload = self._get_json(
            path=f"/rozhodnutie/{guid}",
            params=None,
            context=f"stage=get_decision guid_hash={_guid_hash(guid)}",
        )
        return record_from_infosud_payload(payload, source_base_url=self.base_url, source_guid=guid)

    def _get_json(
        self,
        *,
        path: str,
        params: dict[str, int] | None,
        context: str,
    ) -> dict[str, Any]:
        attempts = max(1, self.retry_attempts)
        for attempt in range(1, attempts + 1):
            try:
                response = httpx.get(
                    f"{self.base_url}{path}",
                    params=params,
                    timeout=self.timeout_seconds,
                    verify=self.tls_verify,
                )
                response.raise_for_status()
                payload = response.json()
                if isinstance(payload, dict):
                    return payload
                return {"data": payload}
            except (httpx.ConnectTimeout, httpx.ReadTimeout, httpx.ConnectError) as exc:
                if attempt >= attempts:
                    self.progress_logger(
                        "infosud_source_request_failed "
                        f"{context} attempt={attempt} max_attempts={attempts} "
                        f"timeout_seconds={self.timeout_seconds:g} error_type={type(exc).__name__} "
                        f"message={_log_safe(str(exc))}"
                    )
                    raise
                self.progress_logger(
                    "infosud_source_request_retry "
                    f"{context} attempt={attempt} max_attempts={attempts} "
                    f"timeout_seconds={self.timeout_seconds:g} error_type={type(exc).__name__} "
                    f"retry_after_seconds={self.retry_backoff_seconds:g} "
                    f"message={_log_safe(str(exc))}"
                )
                if self.retry_backoff_seconds:
                    self.sleep_fn(self.retry_backoff_seconds)

        raise RuntimeError("unreachable InfoSud retry state")


def _refs_from_payload(payload: dict[str, Any]) -> tuple[InfoSudDecisionRef, ...]:
    refs: list[InfoSudDecisionRef] = []
    for item in _extract_items(payload):
        guid = _first_text(item, "guid", "id", "uuid")
        if guid:
            label = _first_text(item, "spisovaZnacka", "cisloSpisu", "ecli", default=guid)
            refs.append(InfoSudDecisionRef(guid=guid, label=label))
    return tuple(refs)


def _non_negative_int(value: object) -> int:
    try:
        return max(0, int(str(value)))
    except (TypeError, ValueError):
        return 0


def record_from_infosud_payload(
    payload: dict[str, Any],
    *,
    source_base_url: str,
    source_guid: str | None = None,
) -> CourtDecisionRecord:
    guid = source_guid or _first_text(payload, "guid", "id", "uuid")
    raw_court = payload.get("sud")
    court: dict[str, Any] = raw_court if isinstance(raw_court, dict) else {}
    raw_original_court = payload.get("povodnySud")
    original_court: dict[str, Any] = raw_original_court if isinstance(raw_original_court, dict) else {}
    court_name = _first_text(
        original_court,
        "nazov",
        "name",
        default=_first_text(court, "nazov", "name", default=_first_text(payload, "sudNazov")),
    )
    court_type = _first_text(court, "typSudu", "typ", default=_first_text(payload, "typSudu"))
    raw_text = _decision_text(payload)
    pseudonymized = pseudonymize_court_decision_text(raw_text)
    source_url = _first_text(payload, "url", "sourceUrl")
    if not source_url:
        source_url = f"{source_base_url.rstrip('/')}/rozhodnutie/{guid}"
    return CourtDecisionRecord(
        source_system="infosud",
        source_guid=guid,
        court_name=court_name,
        court_type=court_type,
        decision_form=_first_text(payload, "formaRozhodnutia"),
        nature=_first_text(payload, "povaha"),
        file_number=_first_text(payload, "spisovaZnacka"),
        case_number=_first_text(payload, "cisloSpisu", "identifikacneCislo"),
        ecli=_first_text(payload, "ecli"),
        issue_date=_first_text(payload, "datumVydania", "vydaneDna"),
        indexed_at=_first_text(payload, "indexDatum", "indexDate"),
        update_date=_first_text(payload, "updateDate"),
        source_url=source_url,
        raw_text=raw_text,
        pseudonymized_text=pseudonymized,
        metadata=payload,
    )


def _extract_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("content", "docs", "items", "rozhodnutia", "rozhodnutieList", "data"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    response = payload.get("response")
    if isinstance(response, dict):
        docs = response.get("docs")
        if isinstance(docs, list):
            return [item for item in docs if isinstance(item, dict)]
    return []


def _first_text(payload: dict[str, Any], *keys: str, default: str = "") -> str:
    for key in keys:
        value = payload.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return default


def _decision_text(payload: dict[str, Any]) -> str:
    text_keys = ("text", "textRozhodnutia", "odovodnenie", "anotacia", "dokumentText")
    parts = [_first_text(payload, key) for key in text_keys]
    joined = "\n\n".join(part for part in parts if part)
    if joined:
        return joined
    return " ".join(
        part
        for part in (
            _first_text(payload, "formaRozhodnutia"),
            _first_text(payload, "povaha"),
            _first_text(payload, "spisovaZnacka"),
            _first_text(payload, "ecli"),
        )
        if part
    )


def _guid_hash(guid: str) -> str:
    return sha256(guid.encode("utf-8")).hexdigest()[:12]


def _log_safe(value: str) -> str:
    return " ".join(value.split())
