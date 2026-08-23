from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata


_COUNT_RE = re.compile(r"\b(?:posledn\w*|najnovs\w*)\s+(\d{1,2})\b")
_PRESENTATION_WORDS = {
    "mi", "ukaz", "ukazte", "zobraz", "zobrazte", "daj", "dajte", "summary",
    "sumar", "zhrnutie", "zhrnutia", "rozhodnutie", "rozhodnuti", "rozhodnutia",
    "sud", "sudu", "sudov", "sudne", "sudnych", "judikat", "judikaty", "judikatura",
    "ohladom", "problem", "problemov", "posledny", "poslednych", "najnovsi", "najnovsich",
    "pripad", "pripady", "pripadov", "propad", "propadov", "ktore", "ktory", "mas",
    "mate", "system", "systeme", "v", "o", "s", "so", "na", "pre", "the", "last",
    "latest", "show", "me", "court", "decisions", "cases", "about",
}


@dataclass(frozen=True)
class CourtDecisionQuery:
    topic_query: str
    tsquery: str
    requested_limit: int | None
    latest_requested: bool
    concepts: tuple[str, ...]


def parse_court_decision_query(query: str) -> CourtDecisionQuery:
    """Turn a conversational request into a selective, bounded search contract."""

    canonical = _canonical(query)
    count_match = _COUNT_RE.search(canonical)
    requested_limit = min(max(int(count_match.group(1)), 1), 50) if count_match else None
    latest_requested = bool(re.search(r"\b(posledn\w*|najnovs\w*|latest|newest|last)\b", canonical))
    tokens = [token for token in re.findall(r"[a-z0-9]+", canonical) if not token.isdigit()]
    topic_tokens = [token for token in tokens if token not in _PRESENTATION_WORDS]
    purchase_contract = (
        any(token.startswith(("kup", "kupon")) for token in topic_tokens)
        and any(token.startswith(("predaj", "zmluv")) for token in topic_tokens)
    ) or (
        any(token.startswith("predaj") for token in topic_tokens)
        and any(token.startswith("zmluv") for token in topic_tokens)
    )
    if purchase_contract:
        return CourtDecisionQuery(
            topic_query="kupna predajna zmluva",
            tsquery=(
                "((kup:* | kúp:*) & zmluv:*) | (predaj:* & zmluv:*) | "
                "((predav:* | predáv:*) & kupuj:*)"
            ),
            requested_limit=requested_limit,
            latest_requested=latest_requested,
            concepts=("purchase_contract",),
        )

    stems = tuple(dict.fromkeys(token[:24] for token in topic_tokens if len(token) >= 3))
    return CourtDecisionQuery(
        topic_query=" ".join(stems) or canonical,
        tsquery=" & ".join(f"{stem}:*" for stem in stems) or "rozhodnut:*",
        requested_limit=requested_limit,
        latest_requested=latest_requested,
        concepts=(),
    )


def _canonical(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.casefold())
    ascii_only = "".join(char for char in normalized if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", ascii_only).strip()
