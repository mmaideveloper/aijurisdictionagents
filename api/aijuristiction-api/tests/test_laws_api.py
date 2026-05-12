from __future__ import annotations

import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

import app.law_citations as law_citations
from app.main import app

AUTH_HEADERS = {"x-api-key": "aijuris"}


def test_download_law_source_streams_local_html_artifact(monkeypatch, tmp_path: Path) -> None:
    laws_db = tmp_path / "laws.sqlite3"
    artifact_path = tmp_path / "source-artifacts" / "sk-zz-1993-1-19930101.html"
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text("<html><body>Law text</body></html>", encoding="utf-8")

    with sqlite3.connect(laws_db) as conn:
        conn.executescript(
            """
            CREATE TABLE law_documents (
                document_id TEXT PRIMARY KEY,
                country_code TEXT NOT NULL,
                collection_code TEXT NOT NULL,
                law_year INTEGER NOT NULL,
                law_number INTEGER NOT NULL,
                official_name TEXT NOT NULL,
                lawyer_title TEXT NOT NULL,
                source_url TEXT NOT NULL
            );
            CREATE TABLE law_versions (
                version_id TEXT PRIMARY KEY,
                document_id TEXT NOT NULL,
                version_token TEXT NOT NULL,
                effective_from TEXT NOT NULL
            );
            CREATE TABLE law_metadata (
                law_metadata_id TEXT PRIMARY KEY,
                document_id TEXT NOT NULL,
                version_id TEXT NOT NULL,
                law_identifier_text TEXT NOT NULL,
                title TEXT NOT NULL
            );
            CREATE TABLE source_artifacts (
                artifact_id TEXT PRIMARY KEY,
                document_id TEXT NOT NULL,
                version_id TEXT NOT NULL,
                artifact_kind TEXT NOT NULL,
                source_url TEXT NOT NULL,
                storage_backend TEXT NOT NULL,
                storage_path TEXT NOT NULL
            );
            """
        )
        conn.execute(
            """
            INSERT INTO law_documents(
                document_id, country_code, collection_code, law_year, law_number,
                official_name, lawyer_title, source_url
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "doc-1",
                "SK",
                "ZZ",
                1993,
                1,
                "Prvy zakon",
                "Prvy zakon",
                "https://www.slov-lex.sk/pravne-predpisy/SK/ZZ/1993/1/",
            ),
        )
        conn.execute(
            """
            INSERT INTO law_versions(version_id, document_id, version_token, effective_from)
            VALUES (?, ?, ?, ?)
            """,
            ("ver-1", "doc-1", "19930101", "1993-01-01"),
        )
        conn.execute(
            """
            INSERT INTO law_metadata(law_metadata_id, document_id, version_id, law_identifier_text, title)
            VALUES (?, ?, ?, ?, ?)
            """,
            ("meta-1", "doc-1", "ver-1", "1/1993 Z. z.", "Prvy zakon"),
        )
        conn.execute(
            """
            INSERT INTO source_artifacts(
                artifact_id, document_id, version_id, artifact_kind, source_url, storage_backend, storage_path
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "art-1",
                "doc-1",
                "ver-1",
                "html",
                "https://www.slov-lex.sk/pravne-predpisy/SK/ZZ/1993/1/",
                "local_file",
                str(artifact_path),
            ),
        )
        conn.commit()

    monkeypatch.setenv("LAWS_DB_BACKEND", "sqlite")
    monkeypatch.setenv("LAWS_DB_LOCAL", str(laws_db))
    monkeypatch.setattr(law_citations, "_REPO_ROOT", tmp_path)

    client = TestClient(app)
    response = client.get(
        "/v1/laws/source",
        params={
            "country_code": "SK",
            "collection_code": "ZZ",
            "law_year": 1993,
            "law_number": 1,
            "version_token": "19930101",
            "artifact_kind": "html",
        },
        headers=AUTH_HEADERS,
    )

    assert response.status_code == 200
    assert response.text == "<html><body>Law text</body></html>"
    assert response.headers["content-type"].startswith("text/html")


def test_get_law_document_text_by_record_id(monkeypatch, tmp_path: Path) -> None:
    laws_db = tmp_path / "laws.sqlite3"

    with sqlite3.connect(laws_db) as conn:
        conn.executescript(
            """
            CREATE TABLE law_versions (
                version_id TEXT PRIMARY KEY,
                document_id TEXT NOT NULL,
                version_token TEXT NOT NULL,
                effective_from TEXT NOT NULL
            );
            CREATE TABLE source_artifacts (
                artifact_id TEXT PRIMARY KEY,
                document_id TEXT NOT NULL,
                version_id TEXT NOT NULL,
                artifact_kind TEXT NOT NULL,
                source_url TEXT NOT NULL,
                storage_backend TEXT NOT NULL,
                storage_path TEXT NOT NULL,
                content_text TEXT NOT NULL,
                fetched_at TEXT NOT NULL
            );
            """
        )
        conn.execute(
            """
            INSERT INTO law_versions(version_id, document_id, version_token, effective_from)
            VALUES (?, ?, ?, ?)
            """,
            ("ver-1", "doc-1", "19930101", "1993-01-01"),
        )
        conn.execute(
            """
            INSERT INTO source_artifacts(
                artifact_id, document_id, version_id, artifact_kind, source_url, storage_backend, storage_path, content_text, fetched_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "art-1",
                "doc-1",
                "ver-1",
                "html",
                "https://www.slov-lex.sk/pravne-predpisy/SK/ZZ/1993/1/",
                "local_file",
                "ignored",
                "Latest law text for record doc-1",
                "2026-05-07T12:00:00+00:00",
            ),
        )
        conn.commit()

    monkeypatch.setenv("LAWS_DB_BACKEND", "sqlite")
    monkeypatch.setenv("LAWS_DB_LOCAL", str(laws_db))
    monkeypatch.setattr(law_citations, "_REPO_ROOT", tmp_path)

    client = TestClient(app)
    response = client.get(
        "/v1/laws/document-text",
        params={"document_id": "doc-1"},
        headers=AUTH_HEADERS,
    )

    assert response.status_code == 200
    assert response.json() == {"document_id": "doc-1", "content_text": "Latest law text for record doc-1"}
