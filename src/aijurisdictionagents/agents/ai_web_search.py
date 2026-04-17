from __future__ import annotations

from dataclasses import dataclass
import html
import json
import re
from urllib.parse import parse_qs, quote_plus, unquote, urlparse
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class WebSearchRecord:
    title: str
    url: str
    snippet: str


@dataclass
class EntityScreeningAgent:
    """Global entity-screening helper that always requires user consent before use."""

    name: str = "EntityScreeningAgent"

    def build_screening_consent_prompt(self, *, entity_type: str, entity_value: str) -> str:
        normalized_type = (entity_type or "entity").strip().lower()
        normalized_value = (entity_value or "").strip() or "unknown"
        return (
            "Before I run internet screening, please confirm permission for this lookup: "
            f"{normalized_type} = '{normalized_value}'. Reply YES to continue or NO to skip."
        )

    def build_structured_screening_prompt(
        self,
        *,
        entity_type: str,
        entity_value: str,
        country: str | None = None,
    ) -> str:
        normalized_type = (entity_type or "entity").strip().lower()
        normalized_value = (entity_value or "").strip() or "unknown"
        normalized_country = (country or "").strip().upper() or "N/A"
        if normalized_type == "company":
            return CompanySearchAgent().build_search_prompt(
                company_reference=normalized_value,
                country=normalized_country,
            )
        if normalized_type == "person":
            return PersonSearchAgent().build_search_prompt(
                person_reference=normalized_value,
                country=normalized_country,
            )
        return (
            "Find public information about the target entity and prepare a concise report with: "
            "address, related companies/associations, debt exposure (social/health/financial), and web findings. "
            f"Entity: {normalized_value}. Country: {normalized_country}."
        )

    def search(self, *, query: str, max_results: int = 5) -> list[WebSearchRecord]:
        encoded_query = quote_plus(query.strip())
        if not encoded_query:
            return []
        records = self._search_duckduckgo_instant_answer(encoded_query=encoded_query, max_results=max_results)
        if records:
            return records
        return self._search_duckduckgo_html(encoded_query=encoded_query, max_results=max_results)

    def _search_duckduckgo_instant_answer(
        self,
        *,
        encoded_query: str,
        max_results: int,
    ) -> list[WebSearchRecord]:
        request = Request(
            url=f"https://duckduckgo.com/?q={encoded_query}&format=json&pretty=0",
            headers={"User-Agent": "aijurisdictionagents/ai-web-search-agent"},
        )
        with urlopen(request, timeout=15) as response:
            payload = json.loads(response.read().decode("utf-8"))
        related = payload.get("RelatedTopics", [])
        records: list[WebSearchRecord] = []
        for item in related:
            if len(records) >= max_results:
                break
            if not isinstance(item, dict):
                continue
            text = str(item.get("Text") or "").strip()
            url = str(item.get("FirstURL") or "").strip()
            if not text or not url:
                nested = item.get("Topics")
                if isinstance(nested, list):
                    for nested_item in nested:
                        if len(records) >= max_results:
                            break
                        if not isinstance(nested_item, dict):
                            continue
                        nested_text = str(nested_item.get("Text") or "").strip()
                        nested_url = str(nested_item.get("FirstURL") or "").strip()
                        if nested_text and nested_url:
                            records.append(
                                WebSearchRecord(
                                    title=nested_text.split(" - ")[0].strip(),
                                    url=nested_url,
                                    snippet=nested_text,
                                )
                            )
                continue
            records.append(
                WebSearchRecord(
                    title=text.split(" - ")[0].strip(),
                    url=url,
                    snippet=text,
                )
            )
        return records

    def _search_duckduckgo_html(
        self,
        *,
        encoded_query: str,
        max_results: int,
    ) -> list[WebSearchRecord]:
        request = Request(
            url=f"https://html.duckduckgo.com/html/?q={encoded_query}",
            headers={"User-Agent": "Mozilla/5.0 (compatible; aijurisdictionagents/ai-web-search-agent)"},
        )
        with urlopen(request, timeout=15) as response:
            payload = response.read().decode("utf-8", errors="ignore")
        return _parse_duckduckgo_html_results(payload=payload, max_results=max_results)


class AIWebSearchAgent(EntityScreeningAgent):
    """Backward-compatible alias for EntityScreeningAgent."""

    name: str = "AIWebSearchAgent"


@dataclass
class CompanySearchAgent(EntityScreeningAgent):
    """Structured company screening prompt helper."""

    name: str = "CompanySearchAgent"

    def build_search_prompt(self, *, company_reference: str, country: str | None = None) -> str:
        normalized_reference = (company_reference or "").strip() or "unknown company"
        normalized_country = (country or "").strip().upper() or "N/A"
        return (
            "Find publicly available information about the company and prepare a summary containing:\n"
            "1. registered address\n"
            "2. list of companies owned by this company\n"
            "3. list of owners or people associated with the company\n"
            "4. list of debts or liabilities, especially in:\n"
            "   - social insurance\n"
            "   - health insurance\n"
            "   - financial institutions\n"
            "5. additional relevant web information\n"
            f"Company reference: {normalized_reference}\n"
            f"Country: {normalized_country}"
        )


@dataclass
class PersonSearchAgent(EntityScreeningAgent):
    """Structured person screening prompt helper."""

    name: str = "PersonSearchAgent"

    def build_search_prompt(self, *, person_reference: str, country: str | None = None) -> str:
        normalized_reference = (person_reference or "").strip() or "unknown person"
        normalized_country = (country or "").strip().upper() or "N/A"
        return (
            "Find publicly available information about the person and prepare a summary containing:\n"
            "1. address\n"
            "2. list of companies linked to the person\n"
            "3. list of trade licenses / sole-trader businesses\n"
            "4. list of debts or liabilities, especially in:\n"
            "   - social insurance\n"
            "   - health insurance\n"
            "   - financial institutions\n"
            "5. additional relevant web information\n"
            f"Person reference: {normalized_reference}\n"
            f"Country: {normalized_country}"
        )


def _parse_duckduckgo_html_results(*, payload: str, max_results: int) -> list[WebSearchRecord]:
    records: list[WebSearchRecord] = []
    matches = re.finditer(
        (
            r'<a[^>]*class="[^"]*result__a[^"]*"[^>]*href="(?P<url>[^"]+)"[^>]*>'
            r'(?P<title>.*?)</a>(?P<tail>.*?)(?=<a[^>]*class="[^"]*result__a[^"]*"|$)'
        ),
        payload,
        flags=re.IGNORECASE | re.DOTALL,
    )
    for match in matches:
        if len(records) >= max_results:
            break
        url = _normalize_search_result_url(match.group("url"))
        title = _strip_html(match.group("title"))
        snippet_match = re.search(
            r'<a[^>]*class="[^"]*result__snippet[^"]*"[^>]*>(?P<snippet>.*?)</a>|'
            r'<div[^>]*class="[^"]*result__snippet[^"]*"[^>]*>(?P<snippet_div>.*?)</div>',
            match.group("tail"),
            flags=re.IGNORECASE | re.DOTALL,
        )
        snippet_raw = ""
        if snippet_match is not None:
            snippet_raw = snippet_match.group("snippet") or snippet_match.group("snippet_div") or ""
        snippet = _strip_html(snippet_raw)
        if not title or not url:
            continue
        records.append(
            WebSearchRecord(
                title=title,
                url=url,
                snippet=snippet or title,
            )
        )
    return records


def _strip_html(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", value))).strip()


def _normalize_search_result_url(value: str) -> str:
    normalized = html.unescape(value).strip()
    if normalized.startswith("//"):
        normalized = f"https:{normalized}"
    parsed = urlparse(normalized)
    if parsed.netloc.endswith("duckduckgo.com") and parsed.path == "/l/":
        encoded_target = parse_qs(parsed.query).get("uddg", [""])[0]
        if encoded_target:
            return unquote(encoded_target).strip()
    return normalized
