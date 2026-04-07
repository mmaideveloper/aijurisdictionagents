from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Any, Callable
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from ..base import ToolDefinition, ToolResult


@dataclass(frozen=True)
class ObchodnyRegisterCompany:
    name: str
    registration_number: str
    seat: str
    status: str
    raw: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "registration_number": self.registration_number,
            "seat": self.seat,
            "status": self.status,
            "raw": self.raw,
        }


class ObchodnyRegisterTool:
    """Search Slovak company records from ORSR search endpoint."""

    base_url = "https://sluzby.orsr.sk/Vyhladavanie"

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
                "(business name, IČO, registered seat, legal status, statutory representatives)."
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

        records = tuple(
            company.as_dict()
            for company in self._parse_response(body=body, content_type=content_type)
        )
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
        params = {
            "CurrentPage": max(current_page, 1),
            "Take": max(take, 1),
            "sortCriteria[0].Direction": "Ascending",
            "sortCriteria[0].FieldName": "PhysicalPersonName",
            "Filter.CorporateBodyFullNameOrRegistrationNumber": company_name_or_registration,
            "Filter.CorporateBodyNameLike": "true",
            "Filter.PhysicalPersonName": person_name,
            "Filter.IncludeTerminated": "true" if include_terminated else "false",
        }
        return f"{self.base_url}?{urlencode(params)}"

    def _parse_response(self, *, body: str, content_type: str) -> tuple[ObchodnyRegisterCompany, ...]:
        cleaned = body.strip()
        if "json" in content_type.lower() or cleaned.startswith("{") or cleaned.startswith("["):
            return _parse_json_payload(cleaned)
        return _parse_html_payload(cleaned)


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
                seat=_pick_first_non_empty(row, "seat", "Seat", "registeredSeat", "RegisteredSeat"),
                status=_pick_first_non_empty(row, "status", "Status", "currentStatus", "CurrentStatus"),
                raw=row,
            )
        )
    return tuple(companies)


def _parse_html_payload(payload: str) -> tuple[ObchodnyRegisterCompany, ...]:
    row_matches = re.findall(r"<tr[^>]*>(.*?)</tr>", payload, flags=re.IGNORECASE | re.DOTALL)
    companies: list[ObchodnyRegisterCompany] = []
    for row_html in row_matches:
        cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row_html, flags=re.IGNORECASE | re.DOTALL)
        normalized_cells = [_collapse_html(cell) for cell in cells]
        normalized_cells = [cell for cell in normalized_cells if cell]
        if not normalized_cells:
            continue
        name = normalized_cells[0]
        registration = _first_registration_number(normalized_cells)
        seat = normalized_cells[2] if len(normalized_cells) > 2 else ""
        status = normalized_cells[3] if len(normalized_cells) > 3 else ""
        if not registration:
            continue
        companies.append(
            ObchodnyRegisterCompany(
                name=name,
                registration_number=registration,
                seat=seat,
                status=status,
                raw={"html_row": row_html, "cells": normalized_cells},
            )
        )
    return tuple(companies)


def _collapse_html(value: str) -> str:
    no_tags = re.sub(r"<[^>]+>", " ", value)
    unescaped = (
        no_tags.replace("&nbsp;", " ")
        .replace("&amp;", "&")
        .replace("&quot;", '"')
        .replace("&#39;", "'")
    )
    return re.sub(r"\s+", " ", unescaped).strip()


def _first_registration_number(cells: list[str]) -> str:
    pattern = re.compile(r"\b\d{6,10}\b")
    for cell in cells:
        match = pattern.search(cell)
        if match:
            return match.group(0)
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
