"""Deterministic citations and a public, read-only view of collected Slovak legislation."""

import re
from urllib.parse import urlencode, urlsplit

import psycopg
from fastapi import HTTPException
from psycopg.rows import dict_row

LAW = re.compile(
    r"(?<![\w/])(?P<prefix>č\.\s*)?(?P<number>\d{1,4})\s*/\s*(?P<year>(?:18|19|20)\d{2})(?!\d)(?P<suffix>\s*Z\.\s*z\.)?",
    re.IGNORECASE,
)


def linked_text(text: str | None, annotations: list, field: str, test_id: str) -> list[dict]:
    """Return text tokens, avoiding Python/JS Unicode offset mismatches and HTML injection.

    Explicit numbered citations are automatic. Bare sections require editorial metadata;
    neither nearby text nor a model is allowed to guess the referenced law.
    """
    text = text or ""
    spans = []
    for annotation in annotations:
        if not isinstance(annotation, dict):
            continue
        if annotation.get("field") != field:
            continue
        quote = annotation.get("quote", "")
        if not isinstance(quote, str) or not quote or text.count(quote) != 1:
            continue  # Stale/ambiguous annotation: leave readable original text.
        if not all(type(annotation.get(k)) is int for k in ("law_number", "law_year")):
            continue
        start = text.index(quote)
        spans.append((start, start + len(quote), annotation))
    for match in LAW.finditer(text):
        if not match["prefix"] and not match["suffix"]:
            continue
        if not any(a < match.end() and b > match.start() for a, b, _ in spans):
            spans.append(
                (
                    match.start(),
                    match.end(),
                    {"law_number": int(match["number"]), "law_year": int(match["year"])},
                )
            )
    tokens = []
    cursor = 0
    for start, end, ref in sorted(spans, key=lambda span: span[0]):
        if start < cursor:
            continue
        if start > cursor:
            tokens.append({"text": text[cursor:start]})
        query = {"test": test_id}
        for key in ("section", "paragraph", "letter"):
            if ref.get(key) and re.fullmatch(r"[0-9a-z]{1,8}", str(ref[key])):
                query[key] = str(ref[key])
        href = f"/laws/{ref['law_year']}/{ref['law_number']}?{urlencode(query)}"
        tokens.append({"text": text[start:end], "href": href})
        cursor = end
    if cursor < len(text):
        tokens.append({"text": text[cursor:]})
    return tokens


def enrich_question(row: dict) -> dict:
    for item in [row, *row["subquestions"]]:
        annotations = item.pop("legal_references", [])
        item["linked_body"] = linked_text(item["body"], annotations, "body", row["test_id"])
        item["linked_answer"] = linked_text(item.get("answer"), annotations, "answer", row["test_id"])
    return row


def anchor_matches(anchor: str, section: str, paragraph: str | None, letter: str | None) -> bool:
    # Native Slov-Lex collector anchors, plus the collector's legacy fixture anchors.
    normalized = anchor.lower().removesuffix(".text")
    normalized = re.sub(r"^(?:paragraf-|par-|par)(\d+[a-z]?)", r"s-\1", normalized)
    normalized = normalized.replace(".odsek-", ".p-").replace(".pismeno-", ".l-")
    target = "s-" + section
    if paragraph:
        target += ".p-" + paragraph
    if letter:
        target += ".l-" + letter
    return normalized == target or normalized.startswith(target + ".")


def read_law(url: str, year: int, number: int, legal_date, section=None, paragraph=None, letter=None):
    if legal_date is None:
        raise HTTPException(
            409, "Test zatiaľ nemá schválený právny dátum. Správne znenie zákona preto nemožno vybrať."
        )
    if not url:
        raise HTTPException(503, "Knižnica zákonov zatiaľ nie je dostupná. Skúste to neskôr.")
    try:
        with psycopg.connect(url, row_factory=dict_row, connect_timeout=5) as conn:
            conn.execute("SET TRANSACTION READ ONLY")
            conn.execute("SET LOCAL statement_timeout = '5000ms'")
            law = conn.execute(
                """SELECT d.document_id,d.law_number,d.law_year,d.official_name AS title,
                v.version_id,v.version_token,v.effective_from,m.effective_to,
                (SELECT a.source_url FROM source_artifacts a WHERE a.version_id=v.version_id
                 AND a.artifact_kind='html' ORDER BY a.fetched_at DESC LIMIT 1) AS source_url
                FROM law_documents d JOIN law_versions v USING(document_id)
                LEFT JOIN law_metadata m USING(version_id)
                WHERE d.country_code='SK' AND d.collection_code='ZZ'
                AND d.law_year=%s AND d.law_number=%s AND v.effective_from<=%s
                ORDER BY v.effective_from DESC,v.version_token DESC LIMIT 1""",
                (year, number, legal_date),
            ).fetchone()
            if not law or (law["effective_to"] and law["effective_to"] < legal_date):
                raise HTTPException(404, "Znenie zákona k právnemu dátumu testu nie je v knižnici dostupné.")
            provisions = conn.execute(
                "SELECT anchor,heading,body_text FROM law_provisions WHERE version_id=%s ORDER BY ordinal,provision_id",
                (law["version_id"],),
            ).fetchall()
    except psycopg.Error:
        raise HTTPException(503, "Knižnica zákonov je dočasne nedostupná. Skúste to neskôr.") from None
    if not provisions:
        raise HTTPException(404, "Text tohto znenia zákona zatiaľ nie je dostupný.")
    # Never expose arbitrary imported links as executable/external navigation.
    source = urlsplit(law["source_url"] or "")
    if (
        source.scheme != "https"
        or source.hostname not in {"static.slov-lex.sk", "www.slov-lex.sk"}
        or source.username
        or source.password
    ):
        law["source_url"] = None
    for provision in provisions:
        provision["highlighted"] = bool(
            section and anchor_matches(provision["anchor"], section, paragraph, letter)
        )
    return {
        **law,
        "legal_date": legal_date,
        "provisions": provisions,
        "target_found": any(p["highlighted"] for p in provisions) if section else None,
    }
