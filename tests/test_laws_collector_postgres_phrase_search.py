from __future__ import annotations

import os
from typing import TypedDict
import unicodedata

import psycopg
import pytest
from psycopg.rows import dict_row


class PhraseMatch(TypedDict):
    law_year: int
    law_number: int
    official_name: str
    lawyer_title: str
    version_token: str
    effective_from: str
    source_url: str


def _normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.casefold())
    return " ".join(normalized.encode("ascii", "ignore").decode("ascii").split())


def _connection_uri() -> str:
    return os.getenv(
        "LAWS_DB_CLOUD",
        "postgresql://postgres:postgres@127.0.0.1:5433/laws_sk",
    )


def _search_phrase_matches(*, connection_uri: str, phrase: str) -> list[PhraseMatch]:
    normalized_phrase = _normalize_text(phrase)
    matches: list[PhraseMatch] = []

    with psycopg.connect(connection_uri, row_factory=dict_row) as conn:
        rows = conn.execute(
            """
            SELECT d.law_year,
                   d.law_number,
                   d.official_name,
                   d.lawyer_title,
                   d.source_url,
                   v.version_token,
                   v.effective_from,
                   COALESCE(a.content_text, '') AS content_text
            FROM law_versions AS v
            JOIN law_documents AS d ON d.document_id = v.document_id
            LEFT JOIN source_artifacts AS a
              ON a.version_id = v.version_id
             AND a.artifact_kind = 'html'
            ORDER BY d.law_year DESC, d.law_number DESC, v.effective_from DESC
            """
        ).fetchall()

    seen_keys: set[tuple[int, int, str]] = set()
    for row in rows:
        haystack = _normalize_text(str(row["content_text"]))
        if normalized_phrase not in haystack:
            continue

        key = (
            int(row["law_year"]),
            int(row["law_number"]),
            str(row["version_token"]),
        )
        if key in seen_keys:
            continue
        seen_keys.add(key)
        matches.append(
            PhraseMatch(
                law_year=int(row["law_year"]),
                law_number=int(row["law_number"]),
                official_name=str(row["official_name"]),
                lawyer_title=str(row["lawyer_title"]),
                version_token=str(row["version_token"]),
                effective_from=str(row["effective_from"]),
                source_url=str(row["source_url"]),
            )
        )

    return matches


@pytest.mark.skipif(
    os.getenv("RUN_LOCAL_POSTGRES_LAWS_SEARCH_TEST") != "1",
    reason="Set RUN_LOCAL_POSTGRES_LAWS_SEARCH_TEST=1 to run against the local PostgreSQL laws DB.",
)
def test_local_postgres_phrase_search_prints_matching_documents() -> None:
    phrase = os.getenv("LAWS_SEARCH_PHRASE", "nájomna zmluva")
    matches = _search_phrase_matches(
        connection_uri=_connection_uri(),
        phrase=phrase,
    )

    print(f"Phrase search: {phrase}")
    print(f"Connection: {_connection_uri()}")
    print(f"Matches: {len(matches)}")
    for match in matches:
        print(
            f"- {match['law_number']}/{match['law_year']} | "
            f"{match['official_name']} | version={match['version_token']} | "
            f"effective_from={match['effective_from']} | {match['source_url']}"
        )

    assert isinstance(matches, list)
