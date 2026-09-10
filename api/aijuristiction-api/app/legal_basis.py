"""Structured source evidence shared by document generation and explicit review.

Source verification is distinct from a legal opinion about applicability. Never
promote a model claim, document title or retrieval timestamp into source freshness.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Any, Literal

from pydantic import BaseModel

WARNING = "Právny základ vyžaduje odborné overenie"


class LegalBasis(BaseModel):
    jurisdiction: str = "SK"
    provision: str
    act_number: str
    official_name: str
    source_id: str
    source_url: str
    version_id: str
    effective_from: str
    as_of: str
    verification: Literal["source_verified", "unverified"]
    reason: str
    human_review_required: bool = True


def basis_from_source(source: dict[str, Any], *, provision: str, as_of: date) -> LegalBasis:
    effective = str(source.get("effective_from") or "")[:10]
    try:
        effective_valid = date.fromisoformat(effective) <= as_of
    except ValueError:
        effective_valid = False
    # A returned section is evidence of the provision in the selected corpus
    # version. Freshness/applicability still require a human-visible qualification.
    verified = bool(effective_valid and source.get("version_id") and source.get("section_found")
                    and source.get("content_text") and source.get("official_name")
                    and source.get("content_scope") == "sections")
    return LegalBasis(
        provision=provision, act_number=f"{source.get('law_number', '')}/{source.get('law_year', '')}",
        official_name=str(source.get("official_name") or ""), source_id=str(source.get("document_id") or ""),
        source_url=str(source.get("source_url") or ""), version_id=str(source.get("version_id") or ""),
        effective_from=effective, as_of=as_of.isoformat(),
        verification="source_verified" if verified else "unverified",
        reason="Provision found in current-effective corpus version; official-source freshness and applicability require review."
        if verified else "Provision or effective version could not be verified.",
    )


def render_basis(items: list[LegalBasis]) -> str:
    lines = ["Právny základ"]
    for item in items:
        lines.append(f"{item.provision}, zákon č. {item.act_number}, {item.official_name}")
        lines.append(f"Zdroj: {item.source_url or item.source_id}; znenie: {item.version_id}; účinnosť od: {item.effective_from}; kontrola: {item.as_of}")
    lines.append(WARNING)
    return "\n".join(lines)


def declared_legal_references(text: str) -> list[tuple[str, str]]:
    """Only pair explicitly declared provisions/acts in the same short sentence."""
    matches = re.findall(r"§\s*(\d+[a-z]?)\b[^\n.;]{0,100}?(\d{1,4}/\d{4})\b", text, flags=re.IGNORECASE)
    return list(dict.fromkeys(matches))[:10]


def resolve_declared_basis(text: str, *, country: str) -> list[LegalBasis]:
    if country.strip().upper() not in {"SK", "SLOVAKIA", "SLOVENSKO"}:
        return []
    from app.chat.mcp_law_context import _call_mcp_tool, _tool_results
    items: list[LegalBasis] = []
    for section, identifier in declared_legal_references(text):
        # getLawText's current section contract accepts integer sections only.
        if not section.isdigit():
            continue
        try:
            number, year = identifier.split("/")
            matches = _tool_results(_call_mcp_tool("searchLaws", {
                "query": identifier, "country_code": "SK", "law_number": int(number),
                "law_year": int(year), "limit": 1,
            }))
            if not matches:
                continue
            source = _call_mcp_tool("getLawText", {"document_id": matches[0]["document_id"],
                "section_start": int(section), "section_end": int(section), "max_chars": 10000})
            item = basis_from_source(source, provision=f"§ {section}", as_of=date.today())
            if item.act_number == identifier:
                items.append(item)
        except Exception:
            # No input, credentials or provider error bodies in logs or artifacts.
            continue
    return items


def annotate_document(text: str, *, country: str) -> str:
    if WARNING in text:
        return text
    basis = render_basis(resolve_declared_basis(text, country=country))
    title, separator, body = text.partition("\n")
    return title + "\n\n" + basis + ("\n\n" + body if separator else "")
