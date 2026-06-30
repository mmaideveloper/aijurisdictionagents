from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from .domain import CourtDecisionRecord
from .pseudonymization import pseudonymize_court_decision_text


@dataclass(frozen=True)
class InfoSudDecisionRef:
    guid: str
    label: str


class InfoSudSourceClient:
    source_system = "infosud"

    def __init__(self, *, base_url: str, timeout_seconds: float = 30.0, tls_verify: bool = True) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.tls_verify = tls_verify

    def list_decisions(self, *, page: int = 0, size: int = 25) -> list[InfoSudDecisionRef]:
        response = httpx.get(
            f"{self.base_url}/rozhodnutie",
            params={"page": page, "size": size},
            timeout=self.timeout_seconds,
            verify=self.tls_verify,
        )
        response.raise_for_status()
        payload = response.json()
        items = _extract_items(payload)
        refs: list[InfoSudDecisionRef] = []
        for item in items:
            guid = _first_text(item, "guid", "id", "uuid")
            if guid:
                label = _first_text(item, "spisovaZnacka", "cisloSpisu", "ecli", default=guid)
                refs.append(InfoSudDecisionRef(guid=guid, label=label))
        return refs

    def get_decision(self, guid: str) -> CourtDecisionRecord:
        response = httpx.get(
            f"{self.base_url}/rozhodnutie/{guid}",
            timeout=self.timeout_seconds,
            verify=self.tls_verify,
        )
        response.raise_for_status()
        return record_from_infosud_payload(response.json(), source_base_url=self.base_url, source_guid=guid)


def record_from_infosud_payload(
    payload: dict[str, Any],
    *,
    source_base_url: str,
    source_guid: str | None = None,
) -> CourtDecisionRecord:
    guid = source_guid or _first_text(payload, "guid", "id", "uuid")
    raw_court = payload.get("sud")
    court: dict[str, Any] = raw_court if isinstance(raw_court, dict) else {}
    court_name = _first_text(court, "nazov", "name", default=_first_text(payload, "sudNazov"))
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
