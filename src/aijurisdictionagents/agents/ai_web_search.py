from __future__ import annotations

from dataclasses import dataclass
import json
from urllib.parse import quote_plus
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class WebSearchRecord:
    title: str
    url: str
    snippet: str


@dataclass
class AIWebSearchAgent:
    """Simple web-search helper that always requires user consent before use."""

    name: str = "AIWebSearchAgent"

    def build_screening_consent_prompt(self, *, entity_type: str, entity_value: str) -> str:
        normalized_type = (entity_type or "entity").strip().lower()
        normalized_value = (entity_value or "").strip() or "unknown"
        return (
            "Before I run internet screening, please confirm permission for this lookup: "
            f"{normalized_type} = '{normalized_value}'. Reply YES to continue or NO to skip."
        )

    def search(self, *, query: str, max_results: int = 5) -> list[WebSearchRecord]:
        encoded_query = quote_plus(query.strip())
        if not encoded_query:
            return []
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
