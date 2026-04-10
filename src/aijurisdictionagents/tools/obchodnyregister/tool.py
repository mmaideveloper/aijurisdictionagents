from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Any, Callable
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import unicodedata

from ..base import ToolDefinition, ToolResult


@dataclass(frozen=True)
class ObchodnyRegisterCompany:
    name: str
    registration_number: str
    seat: str
    status: str
    stakeholders: tuple[dict[str, str], ...]
    statutory_representatives: tuple[dict[str, str], ...]
    authorization_to_execute: str
    deposits: tuple[dict[str, str], ...]
    equity_value: str
    raw: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "registration_number": self.registration_number,
            "seat": self.seat,
            "status": self.status,
            "stakeholders": list(self.stakeholders),
            "statutory_representatives": list(self.statutory_representatives),
            "authorization_to_execute": self.authorization_to_execute,
            "deposits": list(self.deposits),
            "equity_value": self.equity_value,
            "raw": self.raw,
        }


class ObchodnyRegisterTool:
    """Search Slovak company records from the official ORSR JSON endpoint."""

    base_url = "https://sluzby.orsr.sk/api/legal-person"

    def __init__(
        self,
        *,
        requester: Callable[[str], tuple[int, str, str]] | None = None,
    ) -> None:
        self._requester = requester or _default_requester

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="obchodny_register_company_check",
            purpose=(
                "Validate Slovak company identity in Obchodný register "
                "(business name, IČO, registered seat, legal status, statutory representatives, stakeholders)."
            ),
            input_fields=("company_name_or_registration", "person_name", "include_terminated"),
            requires_explicit_user_confirmation=False,
        )

    def run(
        self,
        *,
        company_name_or_registration: str,
        person_name: str = "",
        include_terminated: bool = True,
        current_page: int = 1,
        take: int = 10,
    ) -> ToolResult:
        query = company_name_or_registration.strip()
        if not query:
            return ToolResult(
                tool_name=self.definition.name,
                ok=False,
                records=(),
                message="company_name_or_registration is required.",
            )

        url = self.build_search_url(
            company_name_or_registration=query,
            person_name=person_name,
            include_terminated=include_terminated,
            current_page=current_page,
            take=take,
        )

        try:
            status, content_type, body = self._requester(url)
        except Exception as exc:  # pragma: no cover - network failures are environment-specific.
            return ToolResult(
                tool_name=self.definition.name,
                ok=False,
                records=(),
                message=f"obchodny register request failed: {exc}",
            )

        if status >= 400:
            return ToolResult(
                tool_name=self.definition.name,
                ok=False,
                records=(),
                message=f"obchodny register returned HTTP {status}",
            )

        try:
            companies = self._parse_response(body=body, content_type=content_type)
        except ValueError as exc:
            return ToolResult(
                tool_name=self.definition.name,
                ok=False,
                records=(),
                message=f"obchodny register returned unexpected response: {exc}",
            )

        ranked_companies = _rank_companies(query=query, companies=companies)
        if ranked_companies:
            enriched_first = self._enrich_company(query=query, company=ranked_companies[0])
            ranked_companies = (enriched_first, *ranked_companies[1:])
        records = tuple(company.as_dict() for company in ranked_companies)
        return ToolResult(
            tool_name=self.definition.name,
            ok=True,
            records=records,
            message=f"Found {len(records)} record(s).",
        )

    def build_search_url(
        self,
        *,
        company_name_or_registration: str,
        person_name: str,
        include_terminated: bool,
        current_page: int,
        take: int,
    ) -> str:
        bounded_take = max(take, 1)
        skip = max(current_page - 1, 0) * bounded_take
        params = {
            "Skip": skip,
            "Take": bounded_take,
            "Filter.CorporateBodyFullNameOrRegistrationNumber": company_name_or_registration,
            "Filter.CorporateBodyNameLike": "true",
            "Filter.PhysicalPersonName": person_name,
            "Filter.IncludeTerminated": "true" if include_terminated else "false",
        }
        return f"{self.base_url}?{urlencode(params)}"

    def build_detail_url(self, *, section: str, insert_number: int | str, court: str) -> str:
        params = {
            "oddiel": section,
            "vlozka": insert_number,
            "sud": court,
        }
        return f"https://sluzby.orsr.sk/api/legal-person/extract-full?{urlencode(params)}"

    def _parse_response(self, *, body: str, content_type: str) -> tuple[ObchodnyRegisterCompany, ...]:
        cleaned = body.strip()
        if not cleaned:
            return ()
        if "json" not in content_type.lower() and not cleaned.startswith("{") and not cleaned.startswith("["):
            raise ValueError("expected JSON payload from /api/legal-person")
        return _parse_json_payload(cleaned)

    def _enrich_company(
        self,
        *,
        query: str,
        company: ObchodnyRegisterCompany,
    ) -> ObchodnyRegisterCompany:
        detail_url = _build_detail_url_from_company(company)
        if not detail_url:
            return company
        try:
            status, content_type, body = self._requester(detail_url)
        except Exception:
            return company
        if status >= 400:
            return company
        try:
            detail = _parse_detail_payload(body=body, content_type=content_type)
        except ValueError:
            return company
        return _merge_company_detail(company=company, detail=detail, query=query)


def _default_requester(url: str) -> tuple[int, str, str]:
    request = Request(
        url,
        headers={
            "User-Agent": "aijurisdictionagents/1.0 (+https://github.com/mmaideveloper/aijurisdictionagents)",
            "Accept": "application/json,text/html,*/*",
        },
    )
    with urlopen(request, timeout=30) as response:  # noqa: S310 - trusted configured endpoint.
        status = int(getattr(response, "status", 200))
        content_type = str(response.headers.get("Content-Type", ""))
        body = response.read().decode("utf-8", errors="replace")
    return status, content_type, body


def _parse_json_payload(payload: str) -> tuple[ObchodnyRegisterCompany, ...]:
    data = json.loads(payload)
    rows: Any
    if isinstance(data, list):
        rows = data
    elif isinstance(data, dict):
        rows = (
            data.get("items")
            or data.get("Items")
            or data.get("results")
            or data.get("Results")
            or data.get("data")
            or data.get("Data")
            or []
        )
    else:
        rows = []

    companies: list[ObchodnyRegisterCompany] = []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        companies.append(
            ObchodnyRegisterCompany(
                name=_pick_first_non_empty(
                    row,
                    "corporateBodyFullName",
                    "CorporateBodyFullName",
                    "name",
                    "Name",
                ),
                registration_number=_pick_first_non_empty(
                    row,
                    "registrationNumber",
                    "RegistrationNumber",
                    "ico",
                    "Ico",
                    "businessId",
                ),
                seat=_join_non_empty(
                    _pick_first_non_empty(
                        row,
                        "physicalAddressLine1",
                        "PhysicalAddressLine1",
                    ),
                    _pick_first_non_empty(
                        row,
                        "physicalAddressLine2",
                        "PhysicalAddressLine2",
                    ),
                )
                or _pick_first_non_empty(
                    row,
                    "physicalAddress",
                    "PhysicalAddress",
                    "seat",
                    "Seat",
                    "registeredSeat",
                    "RegisteredSeat",
                ),
                status=_pick_first_non_empty(row, "status", "Status", "currentStatus", "CurrentStatus"),
                stakeholders=(),
                statutory_representatives=(),
                authorization_to_execute="",
                deposits=(),
                equity_value="",
                raw=row,
            )
        )
    return tuple(companies)


def _build_detail_url_from_company(company: ObchodnyRegisterCompany) -> str | None:
    raw_reference = company.raw.get("fileReference")
    if not isinstance(raw_reference, dict):
        return None
    section = str(raw_reference.get("section", "")).strip()
    insert_number = raw_reference.get("insertNumber")
    court = str(raw_reference.get("court", "")).strip()
    if not section or insert_number in (None, "") or not court:
        return None
    params = {
        "oddiel": section,
        "vlozka": insert_number,
        "sud": court,
    }
    return f"https://sluzby.orsr.sk/api/legal-person/extract-full?{urlencode(params)}"


def _parse_detail_payload(*, body: str, content_type: str) -> dict[str, Any]:
    cleaned = body.strip()
    if not cleaned:
        raise ValueError("empty detail payload")
    if "json" not in content_type.lower() and not cleaned.startswith("{") and not cleaned.startswith("["):
        raise ValueError("expected JSON payload from /api/legal-person/extract-full")
    data = json.loads(cleaned)
    if not isinstance(data, dict):
        raise ValueError("detail payload must be an object")
    return data


def _merge_company_detail(
    *,
    company: ObchodnyRegisterCompany,
    detail: dict[str, Any],
    query: str,
) -> ObchodnyRegisterCompany:
    legal_person = detail.get("legalPerson")
    legal_corporate_body = legal_person.get("corporateBody") if isinstance(legal_person, dict) else {}
    corporate_body = legal_corporate_body if isinstance(legal_corporate_body, dict) else {}

    current_name = _pick_current_value(corporate_body.get("corporateBodyFullName")) or company.name
    seat = _extract_company_seat(detail) or company.seat
    registration_number = _extract_registration_number(detail) or company.registration_number
    status = _resolve_company_status(detail=detail, company_name=current_name) or company.status or "Aktívna"
    stakeholders = _extract_stakeholders(detail)
    statutory_representatives = _extract_statutory_representatives(detail)
    authorization_to_execute = _pick_current_value(corporate_body.get("authorizationToExecute"))
    deposits = _extract_deposits(detail)
    equity_value = _extract_equity_value(detail)

    merged_raw = dict(company.raw)
    merged_raw["detail"] = detail
    merged_raw["detail_query"] = query
    return ObchodnyRegisterCompany(
        name=current_name,
        registration_number=registration_number,
        seat=seat,
        status=status,
        stakeholders=stakeholders,
        statutory_representatives=statutory_representatives,
        authorization_to_execute=authorization_to_execute,
        deposits=deposits,
        equity_value=equity_value,
        raw=merged_raw,
    )


def _pick_current_value(values: Any) -> str:
    if isinstance(values, list):
        for item in values:
            if not isinstance(item, dict):
                continue
            if item.get("current") is True:
                value = item.get("value")
                if value is not None and str(value).strip():
                    return str(value).strip()
        for item in values:
            if not isinstance(item, dict):
                continue
            value = item.get("value")
            if value is not None and str(value).strip():
                return str(value).strip()
    if values is None:
        return ""
    return str(values).strip()


def _extract_company_seat(detail: dict[str, Any]) -> str:
    legal_person = detail.get("legalPerson")
    if not isinstance(legal_person, dict):
        return ""
    addresses = legal_person.get("physicalAddress")
    if not isinstance(addresses, list):
        return ""
    for address in addresses:
        if not isinstance(address, dict):
            continue
        if address.get("current") is True:
            return _format_detail_address(address)
    for address in addresses:
        if isinstance(address, dict):
            return _format_detail_address(address)
    return ""


def _extract_registration_number(detail: dict[str, Any]) -> str:
    legal_person = detail.get("legalPerson")
    if not isinstance(legal_person, dict):
        return ""
    identifiers = legal_person.get("id")
    if not isinstance(identifiers, list):
        return ""
    for item in identifiers:
        if not isinstance(item, dict):
            continue
        if item.get("current") is True:
            value = item.get("identifierValue")
            if value is not None and str(value).strip():
                return str(value).strip()
    for item in identifiers:
        if not isinstance(item, dict):
            continue
        value = item.get("identifierValue")
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _resolve_company_status(*, detail: dict[str, Any], company_name: str) -> str:
    normalized_name = _normalize_lookup_text(company_name)
    if "v likvidacii" in normalized_name:
        return "v likvidácii"
    if _has_current_liquidation_marker(detail):
        return "v likvidácii"
    return "Aktívna"


def _has_current_liquidation_marker(detail: dict[str, Any]) -> bool:
    legal_person = detail.get("legalPerson")
    if not isinstance(legal_person, dict):
        return False
    corporate_body = legal_person.get("corporateBody")
    if not isinstance(corporate_body, dict):
        return False
    if _has_current_structural_entry(corporate_body.get("liquidator")):
        return True
    if _has_current_structural_entry(corporate_body.get("liquidatorAuthorizationToExecute")):
        return True
    if _has_current_liquidation_status_event(corporate_body.get("legalStatusEvents")):
        return True
    if _has_current_liquidation_text_marker(corporate_body.get("legalStatus")):
        return True
    if _has_current_liquidation_text_marker(corporate_body.get("otherLegalFacts")):
        return True
    if _has_current_termination_marker(corporate_body.get("termination")):
        return True
    return False


def _has_current_structural_entry(value: Any) -> bool:
    if isinstance(value, list):
        for item in value:
            if not isinstance(item, dict):
                if str(item or "").strip():
                    return True
                continue
            if item.get("current") is True:
                return True
            if "current" not in item and any(str(v or "").strip() for v in item.values()):
                return True
        return False
    if isinstance(value, dict):
        if value.get("current") is True:
            return True
        if "current" not in value and any(str(v or "").strip() for v in value.values()):
            return True
        return False
    return bool(str(value or "").strip())


def _has_current_liquidation_status_event(value: Any) -> bool:
    if not isinstance(value, list):
        return False
    for item in value:
        if not isinstance(item, dict):
            continue
        if item.get("current") is False:
            continue
        event_type = str(item.get("type") or "").strip()
        event_text = str(item.get("text") or "").strip()
        if _contains_liquidation_or_dissolution_marker(event_type):
            return True
        if _contains_liquidation_or_dissolution_marker(event_text):
            return True
    return False


def _has_current_liquidation_text_marker(value: Any) -> bool:
    if isinstance(value, list):
        for item in value:
            if isinstance(item, dict):
                if item.get("current") is False:
                    continue
                for key in ("value", "text", "type", "item", "itemName"):
                    if _contains_liquidation_or_dissolution_marker(str(item.get(key) or "")):
                        return True
                continue
            if _contains_liquidation_or_dissolution_marker(str(item or "")):
                return True
        return False
    if isinstance(value, dict):
        if value.get("current") is False:
            return False
        for key in ("value", "text", "type", "item", "itemName"):
            if _contains_liquidation_or_dissolution_marker(str(value.get(key) or "")):
                return True
        return False
    return _contains_liquidation_or_dissolution_marker(str(value or ""))


def _has_current_termination_marker(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, list):
        for item in value:
            if isinstance(item, dict):
                if item.get("current") is False:
                    continue
                if any(
                    str(item.get(key) or "").strip()
                    for key in ("value", "dateTime", "effectiveFrom", "terminationDate")
                ):
                    return True
                continue
            if str(item or "").strip():
                return True
        return False
    if isinstance(value, dict):
        if value.get("current") is False:
            return False
        return any(
            str(value.get(key) or "").strip()
            for key in ("value", "dateTime", "effectiveFrom", "terminationDate")
        )
    return bool(str(value).strip())


def _contains_liquidation_or_dissolution_marker(value: str) -> bool:
    normalized = _normalize_lookup_text(value)
    if not normalized:
        return False
    return any(marker in normalized for marker in ("likvidac", "likvidator", "zrusen"))


def _extract_stakeholders(detail: dict[str, Any]) -> tuple[dict[str, str], ...]:
    legal_person = detail.get("legalPerson")
    if not isinstance(legal_person, dict):
        return ()
    corporate_body = legal_person.get("corporateBody")
    if not isinstance(corporate_body, dict):
        return ()
    stakeholders = corporate_body.get("stakeholder")
    if not isinstance(stakeholders, list):
        return ()
    extracted: list[dict[str, str]] = []
    for item in stakeholders:
        if not isinstance(item, dict) or item.get("current") is not True:
            continue
        person_data = item.get("personData")
        name = _extract_person_name(person_data)
        address = _extract_person_address(person_data)
        stakeholder_type = _extract_nested_item_name(item.get("stakeholderType"))
        if name:
            extracted.append(
                {
                    "name": name,
                    "address": address,
                    "type": stakeholder_type or "spoločník",
                }
            )
    return tuple(extracted)


def _extract_statutory_representatives(detail: dict[str, Any]) -> tuple[dict[str, str], ...]:
    legal_person = detail.get("legalPerson")
    if not isinstance(legal_person, dict):
        return ()
    corporate_body = legal_person.get("corporateBody")
    if not isinstance(corporate_body, dict):
        return ()
    representatives = corporate_body.get("statutoryBody")
    if not isinstance(representatives, list):
        return ()
    extracted: list[dict[str, str]] = []
    for item in representatives:
        if not isinstance(item, dict) or item.get("current") is not True:
            continue
        person_data = item.get("personData")
        name = _extract_person_name(person_data)
        address = _extract_person_address(person_data)
        function_creation_date = str(item.get("functionCreationDate") or "").strip()
        if name:
            extracted.append(
                {
                    "name": name,
                    "address": address,
                    "function_creation_date": function_creation_date,
                }
            )
    return tuple(extracted)


def _extract_deposits(detail: dict[str, Any]) -> tuple[dict[str, str], ...]:
    legal_person = detail.get("legalPerson")
    if not isinstance(legal_person, dict):
        return ()
    corporate_body = legal_person.get("corporateBody")
    if not isinstance(corporate_body, dict):
        return ()
    deposits = corporate_body.get("deposits")
    if not isinstance(deposits, list):
        return ()
    extracted: list[dict[str, str]] = []
    for item in deposits:
        if not isinstance(item, dict) or item.get("current") is not True:
            continue
        stakeholder_name = _pick_current_value(item.get("stakeholder"))
        currency = _extract_nested_currency(item.get("currency"))
        deposit_value = _format_number_with_currency(item.get("depositValue"), currency)
        deposit_payed_value = _format_number_with_currency(item.get("depositPayedValue"), currency)
        extracted.append(
            {
                "stakeholder_name": stakeholder_name,
                "deposit_value": deposit_value,
                "deposit_payed_value": deposit_payed_value,
            }
        )
    return tuple(extracted)


def _extract_equity_value(detail: dict[str, Any]) -> str:
    legal_person = detail.get("legalPerson")
    if not isinstance(legal_person, dict):
        return ""
    corporate_body = legal_person.get("corporateBody")
    if not isinstance(corporate_body, dict):
        return ""
    equity = corporate_body.get("equity")
    if not isinstance(equity, list):
        return ""
    for item in equity:
        if not isinstance(item, dict) or item.get("current") is not True:
            continue
        currency = _extract_nested_currency(item.get("currency"))
        return _format_number_with_currency(item.get("equityValue"), currency)
    return ""


def _extract_nested_currency(value: Any) -> str:
    if isinstance(value, dict):
        item = value.get("item")
        if isinstance(item, dict):
            codelist_item = item.get("codelistItem")
            if isinstance(codelist_item, dict):
                item_name = codelist_item.get("itemName")
                if item_name is not None and str(item_name).strip():
                    return str(item_name).strip()
            item_value = item.get("item")
            if item_value is not None and str(item_value).strip():
                return str(item_value).strip()
        direct_item = value.get("item")
        if direct_item is not None and not isinstance(direct_item, dict) and str(direct_item).strip():
            return str(direct_item).strip()
    return ""


def _format_number_with_currency(value: Any, currency: str) -> str:
    if value in (None, "", 0) and not currency:
        return ""
    if isinstance(value, (int, float)):
        if isinstance(value, float) and value.is_integer():
            text = str(int(value))
        else:
            text = f"{value}".rstrip("0").rstrip(".")
            text = text.replace(".", ",")
    else:
        text = str(value).strip()
        if text.endswith(".0"):
            text = text[:-2]
        if text:
            text = text.replace(".", ",")
    if text and currency:
        return f"{text} {currency}".strip()
    return text or currency


def _extract_person_name(person_data: Any) -> str:
    if not isinstance(person_data, dict):
        return ""
    physical_person = person_data.get("physicalPerson")
    if isinstance(physical_person, dict):
        person_name = physical_person.get("personName")
        if isinstance(person_name, dict):
            formatted_name = person_name.get("formattedName")
            if formatted_name is not None and str(formatted_name).strip():
                return str(formatted_name).strip()
    corporate_body = person_data.get("corporateBody")
    if isinstance(corporate_body, dict):
        names = corporate_body.get("corporateBodyFullName")
        picked = _pick_current_value(names)
        if picked:
            return picked
    return ""


def _extract_person_address(person_data: Any) -> str:
    if not isinstance(person_data, dict):
        return ""
    addresses = person_data.get("physicalAddress")
    if not isinstance(addresses, list):
        return ""
    for address in addresses:
        if not isinstance(address, dict):
            continue
        return _format_detail_address(address)
    return ""


def _format_detail_address(address: dict[str, Any]) -> str:
    municipality = address.get("municipality")
    municipality_name = ""
    if isinstance(municipality, dict):
        municipality_item = municipality.get("item")
        if municipality_item is not None:
            municipality_name = str(municipality_item).strip()
    country = address.get("country")
    country_name = ""
    if isinstance(country, dict):
        country_item = country.get("item")
        if country_item is not None:
            country_name = str(country_item).strip()
    postal = ""
    delivery = address.get("deliveryAddress")
    if isinstance(delivery, dict):
        postal = str(delivery.get("postalCode") or "").strip()
        if postal and len(postal) == 5:
            postal = f"{postal[:3]} {postal[3:]}"
    street = str(address.get("streetName") or "").strip()
    building_number = str(address.get("buildingNumber") or "").strip()
    line1 = " ".join(part for part in (street, building_number) if part)
    city_line = " ".join(part for part in (postal, municipality_name) if part)
    return _join_non_empty(line1, city_line, country_name)


def _extract_nested_item_name(value: Any) -> str:
    if not isinstance(value, dict):
        return ""
    item = value.get("item")
    if isinstance(item, dict):
        codelist_item = item.get("codelistItem")
        if isinstance(codelist_item, dict):
            item_name = codelist_item.get("itemName")
            if item_name is not None and str(item_name).strip():
                return str(item_name).strip()
    return ""


def _pick_first_non_empty(source: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = source.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def _join_non_empty(*values: str) -> str:
    parts = [value.strip() for value in values if value and value.strip()]
    return ", ".join(parts)


def _rank_companies(
    *,
    query: str,
    companies: tuple[ObchodnyRegisterCompany, ...],
) -> tuple[ObchodnyRegisterCompany, ...]:
    return tuple(sorted(companies, key=lambda company: _company_sort_key(query=query, company=company)))


def _company_sort_key(
    *,
    query: str,
    company: ObchodnyRegisterCompany,
) -> tuple[int, int, int, int, str]:
    normalized_query = _normalize_lookup_text(query)
    query_registration = _normalize_registration(query)
    normalized_name = _normalize_lookup_text(company.name)
    registration = _normalize_registration(company.registration_number)

    exact_registration = 0 if query_registration and query_registration == registration else 1
    exact_name = 0 if normalized_query and normalized_query == normalized_name else 1
    prefix_match = 0 if normalized_query and normalized_name.startswith(normalized_query) else 1
    contains_match = 0 if normalized_query and normalized_query in normalized_name else 1
    return (
        exact_registration,
        exact_name,
        prefix_match,
        contains_match,
        normalized_name,
    )


def _normalize_registration(value: str) -> str:
    return re.sub(r"\D+", "", value or "")


def _normalize_lookup_text(value: str) -> str:
    normalized = "".join(
        char
        for char in unicodedata.normalize("NFD", value.lower())
        if unicodedata.category(char) != "Mn"
    )
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()
