from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata


_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")
_ANCHOR_PATTERN = re.compile(r"(?:^|\.)paragraf-(?P<section>\d+)(?:\.odsek-(?P<paragraph>\d+))?")
_STOP_WORDS = {
    "aby",
    "ako",
    "chcem",
    "ktora",
    "ktore",
    "ktory",
    "na",
    "pre",
    "sa",
    "the",
    "this",
    "vytvor",
    "vytvorit",
    "zmluvu",
}
_CANONICAL_ROOTS = (
    "kup",
    "predaj",
    "zmluv",
    "zahrad",
    "pozem",
    "parcel",
    "nehnutel",
    "dom",
    "byt",
    "prevod",
    "vlastnict",
    "katastr",
    "vklad",
    "cena",
    "predav",
    "kupuj",
    "vad",
    "skod",
    "zodpoved",
    "plnen",
    "odovzd",
    "prevzi",
    "uschov",
)
_SEARCH_VARIANTS: dict[str, tuple[str, ...]] = {
    "kup": ("kup", "kúp"),
    "predaj": ("predaj",),
    "zmluv": ("zmluv",),
    "zahrad": ("zahrad", "záhrad"),
    "pozem": ("pozem",),
    "parcel": ("parcel",),
    "nehnutel": ("nehnutel", "nehnuteľ"),
    "dom": ("dom",),
    "byt": ("byt",),
    "prevod": ("prevod",),
    "vlastnict": ("vlastnict", "vlastníct"),
    "katastr": ("katastr",),
    "vklad": ("vklad",),
    "cena": ("cen",),
    "predav": ("predav", "predáv"),
    "kupuj": ("kupuj", "kupujúc"),
    "vad": ("vad",),
    "skod": ("skod", "škod"),
    "zodpoved": ("zodpoved",),
    "plnen": ("plnen",),
    "odovzd": ("odovzd",),
    "prevzi": ("prevzi",),
    "uschov": ("uschov",),
}


@dataclass(frozen=True)
class LegalQueryConcept:
    name: str
    triggers: frozenset[str]
    expansions: frozenset[str]


@dataclass(frozen=True)
class LegalQueryProfile:
    normalized_query: str
    query_roots: tuple[str, ...]
    expanded_roots: tuple[str, ...]
    search_terms: tuple[str, ...]
    concepts: tuple[str, ...]


@dataclass(frozen=True)
class ParsedProvisionAnchor:
    section_number: int
    paragraph_number: int | None


@dataclass(frozen=True)
class ProvisionRelevance:
    score: float
    matched_terms: tuple[str, ...]


_CONCEPTS = (
    LegalQueryConcept(
        name="purchase_contract",
        triggers=frozenset({"kup", "predaj"}),
        expansions=frozenset(
            {
                "kup",
                "predaj",
                "zmluv",
                "prevod",
                "cena",
                "predav",
                "kupuj",
                "vad",
                "skod",
                "zodpoved",
                "plnen",
                "odovzd",
                "prevzi",
                "uschov",
            }
        ),
    ),
    LegalQueryConcept(
        name="real_estate",
        triggers=frozenset({"zahrad", "pozem", "parcel", "nehnutel", "dom", "byt"}),
        expansions=frozenset(
            {"zahrad", "pozem", "parcel", "nehnutel", "prevod", "vlastnict", "katastr", "vklad"}
        ),
    ),
)


def normalize_legal_text(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.lower())
    without_marks = "".join(character for character in decomposed if not unicodedata.combining(character))
    return " ".join(_TOKEN_PATTERN.findall(without_marks))


def build_legal_query_profile(query: str) -> LegalQueryProfile:
    normalized_query = normalize_legal_text(query)
    query_roots = _query_roots(normalized_query)
    selected_concepts = list(
        concept for concept in _CONCEPTS if concept.triggers.intersection(query_roots)
    )
    selected_names = {concept.name for concept in selected_concepts}
    # A qualified purchase-agreement request needs both the substantive contract rules and
    # property-transfer formalities. Keep a bare ``predaj`` query ambiguous: only expand when
    # the user has actually asked for a purchase/sale agreement.
    if (
        "purchase_contract" in selected_names
        and any(token.startswith("zmluv") for token in _TOKEN_PATTERN.findall(normalized_query))
        and "real_estate" not in selected_names
    ):
        selected_concepts.append(
            next(concept for concept in _CONCEPTS if concept.name == "real_estate")
        )
    expanded_roots = tuple(
        sorted({root for concept in selected_concepts for root in concept.expansions}.difference(query_roots))
    )
    search_terms = tuple(
        sorted(
            {
                variant
                for root in (*query_roots, *expanded_roots)
                for variant in _SEARCH_VARIANTS.get(root, (root,))
                if len(variant) >= 3
            }
        )
    )
    return LegalQueryProfile(
        normalized_query=normalized_query,
        query_roots=query_roots,
        expanded_roots=expanded_roots,
        search_terms=search_terms,
        concepts=tuple(concept.name for concept in selected_concepts),
    )


def build_postgres_legal_tsquery(profile: LegalQueryProfile) -> str:
    """Build a selective prefix query suitable for the provision GIN index.

    Supported concepts use paired legal terms instead of one large OR expression. A large OR
    matched too much of the production corpus and made PostgreSQL prefer a sequential scan even
    though the expression GIN index was present.
    """

    return " | ".join(f"({query})" for query in build_postgres_legal_tsqueries(profile))


def build_postgres_legal_tsqueries(profile: LegalQueryProfile) -> tuple[str, ...]:
    """Return selective per-concept queries so one concept cannot consume every candidate."""

    queries: list[str] = []
    if "purchase_contract" in profile.concepts:
        queries.append(
            f"({_tsquery_variant_group('kup')} <-> {_tsquery_variant_group('zmluv')})"
            f" | ({_tsquery_variant_group('predaj')} <-> {_tsquery_variant_group('zmluv')})"
            f" | ({_tsquery_variant_group('predav')} & {_tsquery_variant_group('kupuj')})"
        )
    if "real_estate" in profile.concepts:
        queries.append(
            f"({_tsquery_variant_group('prevod')} <-> {_tsquery_variant_group('nehnutel')})"
            f" | ({_tsquery_variant_group('vklad')} & {_tsquery_variant_group('zmluv')}"
            f" & {_tsquery_variant_group('katastr')})"
            f" | ({_tsquery_variant_group('navrh')} & {_tsquery_variant_group('vklad')}"
            f" & {_tsquery_variant_group('zmluv')})"
            f" | ({_tsquery_variant_group('parcel')} & {_tsquery_variant_group('podpis')}"
            f" & {_tsquery_variant_group('zmluv')})"
        )
    if queries:
        return tuple(queries)
    fallback = " | ".join(f"{term}:*" for term in profile.search_terms)
    return (fallback,) if fallback else ()


def parse_provision_anchor(anchor: str) -> ParsedProvisionAnchor | None:
    match = _ANCHOR_PATTERN.search(anchor)
    if match is None:
        return None
    paragraph = match.group("paragraph")
    return ParsedProvisionAnchor(
        section_number=int(match.group("section")),
        paragraph_number=int(paragraph) if paragraph is not None else None,
    )


def score_provision_text(
    *,
    profile: LegalQueryProfile,
    title: str,
    heading: str,
    body_text: str,
    database_rank: float = 0.0,
) -> ProvisionRelevance:
    normalized_title = normalize_legal_text(title)
    normalized_provision = normalize_legal_text(f"{heading} {body_text}")
    direct_matches = tuple(
        root for root in profile.query_roots if _contains_root(normalized_title, normalized_provision, root)
    )
    expanded_matches = tuple(
        root for root in profile.expanded_roots if _contains_root(normalized_title, normalized_provision, root)
    )
    title_direct = sum(1 for root in direct_matches if _contains_root(normalized_title, "", root))
    title_expanded = sum(1 for root in expanded_matches if _contains_root(normalized_title, "", root))
    matched_concepts = sum(
        1
        for concept in _CONCEPTS
        if concept.name in profile.concepts
        and concept.expansions.intersection((*direct_matches, *expanded_matches))
    )
    score = (
        len(direct_matches) * 3.0
        + len(expanded_matches) * 1.5
        + title_direct * 6.0
        + title_expanded * 4.0
        + matched_concepts * 3.0
        + max(database_rank, 0.0) * 10.0
    )
    return ProvisionRelevance(
        score=score,
        matched_terms=tuple(sorted(set((*direct_matches, *expanded_matches)))),
    )


def relevance_confidence(score: float) -> str:
    if score >= 16.0:
        return "high"
    if score >= 5.0:
        return "medium"
    return "low"


def compact_section_ranges(
    sections: set[int] | list[int] | tuple[int, ...], *, maximum_gap: int = 2
) -> tuple[tuple[int, int], ...]:
    ordered = sorted(set(sections))
    if not ordered:
        return ()
    ranges: list[tuple[int, int]] = []
    start = ordered[0]
    end = ordered[0]
    for section in ordered[1:]:
        if section - end <= maximum_gap:
            end = section
            continue
        ranges.append((start, end))
        start = section
        end = section
    ranges.append((start, end))
    return tuple(ranges)


def _query_roots(normalized_query: str) -> tuple[str, ...]:
    roots: set[str] = set()
    for token in _TOKEN_PATTERN.findall(normalized_query):
        if token in _STOP_WORDS or len(token) < 3:
            continue
        canonical = next((root for root in _CANONICAL_ROOTS if token.startswith(root)), None)
        roots.add(canonical or token)
    return tuple(sorted(roots))


def _contains_root(normalized_title: str, normalized_provision: str, root: str) -> bool:
    return any(token.startswith(root) for token in _TOKEN_PATTERN.findall(f"{normalized_title} {normalized_provision}"))


def _tsquery_variant_group(root: str) -> str:
    variants = _SEARCH_VARIANTS.get(root, (root,))
    return "(" + " | ".join(f"{variant}:*" for variant in variants) + ")"
