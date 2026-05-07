from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import html
import re
from typing import Callable
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import unicodedata

from ..base import ToolDefinition, ToolResult


_NO_RESULT_PATTERN = re.compile(
    r'Pre\s+„[^”]+”\s+sme\s+nenašli\s+žiadne\s+výsledky\s+v\s+zozname\s+dlžníkov\.',
    flags=re.IGNORECASE,
)
_SNAPSHOT_DATE_PATTERN = re.compile(
    r"Zoznam dlžníkov k dátumu\s+(?P<value>\d{1,2}\.\s*[A-Za-zÁÄČĎÉÍĹĽŇÓÔŔŠŤÚÝŽáäčďéíĺľňóôŕšťúýž]+\s+\d{4})",
    flags=re.IGNORECASE,
)
_ITEM_PATTERN = re.compile(
    r'<li class="dlznici__item">(?P<body>.*?)</li>\s*(?=<li class="dlznici__item">|</ul>)',
    flags=re.IGNORECASE | re.DOTALL,
)
_NAME_PATTERN = re.compile(r'<p class="item-name"[^>]*>(?P<value>.*?)</p>', flags=re.IGNORECASE | re.DOTALL)
_ADDRESS_PATTERN = re.compile(r'<p class="item-adress">(?P<value>.*?)</p>', flags=re.IGNORECASE | re.DOTALL)
_ICON_TITLE_PATTERN = re.compile(r'<img class="item-icon"[^>]*title="(?P<value>[^"]+)"', flags=re.IGNORECASE)
_AMOUNT_PATTERN = re.compile(r'<div class="item-sum">(?P<value>.*?)</div>', flags=re.IGNORECASE | re.DOTALL)
_PAYMENT_PATTERN = re.compile(
    r"window\.location\.href='(?P<value>[^']*action=payment[^']*)'",
    flags=re.IGNORECASE,
)
_CLAIM_PATTERN = re.compile(
    r"window\.location\.href='(?P<value>[^']*action=claim[^']*)'",
    flags=re.IGNORECASE,
)
_ADVISORY_PATTERN = re.compile(
    r"Údaje v uvedenom zozname preto majú len informatívny charakter,.*?nenahrádzajú potvrdenia o stave pohľadávok\.",
    flags=re.IGNORECASE | re.DOTALL,
)


@dataclass(frozen=True)
class DoveraDebtorRecord:
    search_query: str
    checked_at_utc: str
    source_url: str
    source_snapshot_date: str | None
    source_snapshot_date_iso: str | None
    match_confidence: float
    match_type: str
    debtor_name: str
    address: str
    registration_number: str
    debt_amount_display: str
    debt_amount_eur: float | None
    debtor_category: str
    payment_url: str | None
    claim_url: str | None
    evidence_summary: str
    advisory_notice: str
    advisory_only: bool = True

    def as_dict(self) -> dict[str, object]:
        return {
            "search_query": self.search_query,
            "checked_at_utc": self.checked_at_utc,
            "source_url": self.source_url,
            "source_snapshot_date": self.source_snapshot_date,
            "source_snapshot_date_iso": self.source_snapshot_date_iso,
            "match_confidence": self.match_confidence,
            "match_type": self.match_type,
            "debtor_name": self.debtor_name,
            "address": self.address,
            "registration_number": self.registration_number,
            "debt_amount_display": self.debt_amount_display,
            "debt_amount_eur": self.debt_amount_eur,
            "debtor_category": self.debtor_category,
            "payment_url": self.payment_url,
            "claim_url": self.claim_url,
            "evidence_summary": self.evidence_summary,
            "advisory_notice": self.advisory_notice,
            "advisory_only": self.advisory_only,
        }


class DoveraDebtorCheckTool:
    """Search the public Dôvera debtor list and normalize evidence for screening flows."""

    base_url = "https://www.dovera.sk/overenia/dlznici/zoznam-dlznikov"

    def __init__(self, *, requester: Callable[[str], tuple[int, str, str]] | None = None) -> None:
        self._requester = requester or _default_requester

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="dovera_debtor_check",
            purpose=(
                "Check the public Dôvera debtor list for a Slovak person/company query and return "
                "structured health-insurance debt evidence with match confidence and source freshness."
            ),
            input_fields=("search_query",),
            requires_explicit_user_confirmation=True,
        )

    def run(self, *, search_query: str) -> ToolResult:
        query = (search_query or "").strip()
        if not query:
            return ToolResult(
                tool_name=self.definition.name,
                ok=False,
                records=(),
                message="search_query is required.",
            )

        url = self.build_search_url(search_query=query)
        try:
            status, content_type, body = self._requester(url)
        except Exception as exc:  # pragma: no cover - network behavior depends on environment.
            return ToolResult(
                tool_name=self.definition.name,
                ok=False,
                records=(),
                message=f"Dôvera debtor lookup failed: {exc}",
            )
        if status >= 400:
            return ToolResult(
                tool_name=self.definition.name,
                ok=False,
                records=(),
                message=f"Dôvera debtor lookup returned HTTP {status}",
            )

        try:
            parsed = self._parse_page(body=body, content_type=content_type, search_query=query, source_url=url)
        except ValueError as exc:
            return ToolResult(
                tool_name=self.definition.name,
                ok=False,
                records=(),
                message=f"Dôvera debtor lookup returned unexpected response: {exc}",
            )

        if not parsed:
            return ToolResult(
                tool_name=self.definition.name,
                ok=True,
                records=(),
                message="No Dôvera debtor records found.",
            )
        return ToolResult(
            tool_name=self.definition.name,
            ok=True,
            records=tuple(record.as_dict() for record in parsed),
            message=f"Found {len(parsed)} Dôvera debtor record(s).",
        )

    def build_search_url(self, *, search_query: str) -> str:
        return f"{self.base_url}?{urlencode({'q': search_query})}"

    def _parse_page(
        self,
        *,
        body: str,
        content_type: str,
        search_query: str,
        source_url: str,
    ) -> tuple[DoveraDebtorRecord, ...]:
        cleaned = body.strip()
        if not cleaned:
            raise ValueError("empty response body")
        if "html" not in content_type.lower() and "<html" not in cleaned.lower():
            raise ValueError("expected HTML payload")
        if _NO_RESULT_PATTERN.search(cleaned):
            return ()

        snapshot_date_raw = _extract_optional(cleaned, _SNAPSHOT_DATE_PATTERN)
        snapshot_date_iso = _normalize_snapshot_date(snapshot_date_raw)
        advisory_notice = _strip_html(_extract_optional(cleaned, _ADVISORY_PATTERN) or "")
        checked_at_utc = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

        records: list[DoveraDebtorRecord] = []
        for match in _ITEM_PATTERN.finditer(cleaned):
            item_body = match.group("body")
            name = _strip_html(_extract_required(item_body, _NAME_PATTERN, "debtor name"))
            address_block = _extract_required(item_body, _ADDRESS_PATTERN, "debtor address")
            address = _extract_address(address_block)
            registration_number = _extract_registration_number(address_block)
            category = html.unescape(_extract_optional(item_body, _ICON_TITLE_PATTERN) or "").strip()
            amount_display_raw = _extract_required(item_body, _AMOUNT_PATTERN, "debt amount")
            amount_display = _strip_html(amount_display_raw).replace(" €", " €").strip()
            payment_url = _normalize_relative_url(_extract_optional(item_body, _PAYMENT_PATTERN))
            claim_url = _normalize_relative_url(_extract_optional(item_body, _CLAIM_PATTERN))
            match_type, match_confidence = _score_match(
                query=search_query,
                debtor_name=name,
                registration_number=registration_number,
                address=address,
            )
            evidence_summary = (
                f"{name}; {address}; IČO: {registration_number}; {amount_display}; "
                f"snapshot={snapshot_date_raw or 'unknown'}"
            )
            records.append(
                DoveraDebtorRecord(
                    search_query=search_query,
                    checked_at_utc=checked_at_utc,
                    source_url=source_url,
                    source_snapshot_date=snapshot_date_raw,
                    source_snapshot_date_iso=snapshot_date_iso,
                    match_confidence=match_confidence,
                    match_type=match_type,
                    debtor_name=name,
                    address=address,
                    registration_number=registration_number,
                    debt_amount_display=amount_display,
                    debt_amount_eur=_parse_amount_to_float(amount_display),
                    debtor_category=category,
                    payment_url=payment_url,
                    claim_url=claim_url,
                    evidence_summary=evidence_summary,
                    advisory_notice=advisory_notice,
                )
            )
        return tuple(records)


def _default_requester(url: str) -> tuple[int, str, str]:
    request = Request(
        url,
        headers={
            "User-Agent": "aijurisdictionagents/1.0 (+https://github.com/mmaideveloper/aijurisdictionagents)",
            "Accept": "text/html,application/xhtml+xml,*/*",
        },
    )
    with urlopen(request, timeout=30) as response:  # noqa: S310 - trusted configured endpoint.
        status = int(getattr(response, "status", 200))
        content_type = str(response.headers.get("Content-Type", ""))
        body = response.read().decode("utf-8", errors="replace")
    return status, content_type, body


def _extract_required(payload: str, pattern: re.Pattern[str], label: str) -> str:
    match = pattern.search(payload)
    if match is None:
        raise ValueError(f"missing {label}")
    value = match.group("value") if "value" in pattern.groupindex else match.group(0)
    return value.strip()


def _extract_optional(payload: str, pattern: re.Pattern[str]) -> str | None:
    match = pattern.search(payload)
    if match is None:
        return None
    value = match.group("value") if "value" in pattern.groupindex else match.group(0)
    return value.strip()


def _extract_address(raw_address_block: str) -> str:
    address_part = re.split(r"<br\s*/?>", raw_address_block, maxsplit=1, flags=re.IGNORECASE)[0]
    return _strip_html(address_part)


def _extract_registration_number(raw_address_block: str) -> str:
    match = re.search(r"IČO:\s*([0-9]+)", raw_address_block, flags=re.IGNORECASE)
    return match.group(1) if match is not None else ""


def _strip_html(value: str) -> str:
    without_tags = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", html.unescape(without_tags)).strip()


def _normalize_relative_url(value: str | None) -> str | None:
    if not value:
        return None
    normalized = html.unescape(value).strip()
    if normalized.startswith("/"):
        return f"https://www.dovera.sk{normalized}"
    return normalized


def _parse_amount_to_float(value: str) -> float | None:
    normalized = (
        value.replace("\xa0", "")
        .replace("€", "")
        .replace(" ", "")
        .replace(".", "")
        .replace(",", ".")
        .strip()
    )
    if not normalized:
        return None
    try:
        return float(normalized)
    except ValueError:
        return None


def _score_match(
    *,
    query: str,
    debtor_name: str,
    registration_number: str,
    address: str,
) -> tuple[str, float]:
    normalized_query = _normalize_for_match(query)
    normalized_name = _normalize_for_match(debtor_name)
    normalized_address = _normalize_for_match(address)
    digits_query = re.sub(r"\D+", "", query)
    if digits_query and registration_number and digits_query == registration_number:
        return ("exact_registration_number", 1.0)
    if normalized_query and normalized_query == normalized_name:
        return ("exact_name", 0.99)
    if normalized_query and normalized_query in normalized_name:
        return ("partial_name", 0.9)

    query_tokens = {token for token in normalized_query.split() if token}
    if not query_tokens:
        return ("unknown", 0.5)
    name_overlap = len(query_tokens & set(normalized_name.split()))
    address_overlap = len(query_tokens & set(normalized_address.split()))
    token_ratio = max(name_overlap, address_overlap) / len(query_tokens)
    if token_ratio >= 0.75:
        return ("strong_token_overlap", 0.8)
    if token_ratio >= 0.4:
        return ("weak_token_overlap", 0.65)
    return ("low_confidence", 0.45)


def _normalize_for_match(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    without_accents = "".join(character for character in normalized if not unicodedata.combining(character))
    lowered = without_accents.casefold()
    lowered = re.sub(r"[^a-z0-9]+", " ", lowered)
    return re.sub(r"\s+", " ", lowered).strip()


def _normalize_snapshot_date(value: str | None) -> str | None:
    if not value:
        return None
    match = re.match(
        r"(?P<day>\d{1,2})\.\s*(?P<month>[A-Za-zÁÄČĎÉÍĹĽŇÓÔŔŠŤÚÝŽáäčďéíĺľňóôŕšťúýž]+)\s+(?P<year>\d{4})",
        value.strip(),
    )
    if match is None:
        return None
    month_token = _normalize_for_match(match.group("month"))
    month_number = _SLOVAK_MONTHS.get(month_token)
    if month_number is None:
        return None
    return f"{match.group('year')}-{month_number:02d}-{int(match.group('day')):02d}"


_SLOVAK_MONTHS = {
    "januar": 1,
    "februar": 2,
    "marec": 3,
    "april": 4,
    "maj": 5,
    "jun": 6,
    "jul": 7,
    "august": 8,
    "september": 9,
    "oktober": 10,
    "november": 11,
    "december": 12,
}
