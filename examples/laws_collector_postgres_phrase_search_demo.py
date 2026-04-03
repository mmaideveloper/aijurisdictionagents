from __future__ import annotations

import os
import unicodedata

import psycopg
from psycopg.rows import dict_row


def _normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.casefold())
    return " ".join(normalized.encode("ascii", "ignore").decode("ascii").split())


def main() -> None:
    connection_uri = os.getenv(
        "LAWS_DB_CLOUD",
        "postgresql://postgres:postgres@127.0.0.1:5433/laws_sk",
    )
    phrase = os.getenv("LAWS_SEARCH_PHRASE", "nájomna zmluva")
    normalized_phrase = _normalize_text(phrase)

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
    matches: list[dict[str, object]] = []
    for row in rows:
        if normalized_phrase not in _normalize_text(str(row["content_text"])):
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
            {
                "law_year": int(row["law_year"]),
                "law_number": int(row["law_number"]),
                "official_name": str(row["official_name"]),
                "lawyer_title": str(row["lawyer_title"]),
                "version_token": str(row["version_token"]),
                "effective_from": str(row["effective_from"]),
                "source_url": str(row["source_url"]),
            }
        )

    print(f"Phrase search: {phrase}")
    print(f"Connection: {connection_uri}")
    print(f"Matches: {len(matches)}")
    for match in matches:
        print(
            f"- {match['law_number']}/{match['law_year']} | "
            f"{match['official_name']} | version={match['version_token']} | "
            f"effective_from={match['effective_from']} | {match['source_url']}"
        )


if __name__ == "__main__":
    main()
