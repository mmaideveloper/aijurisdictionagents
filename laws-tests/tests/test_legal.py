from dataclasses import replace
import json

from fastapi.testclient import TestClient
import pytest

from laws_tests.app import create_app
from laws_tests.config import Settings
from laws_tests.db import connect
from laws_tests.legal import anchor_matches, linked_text
from reader_fixture import prepare, cleanup, MANIFEST


def test_linking_preserves_text_and_requires_explicit_attribution():
    text = "🧭 § 1 vyhlášky č. 555/2003 Z. z. a zákona č. 190/2003 Z. z."
    tokens = linked_text(text, [], "body", "test & one")
    assert "".join(t["text"] for t in tokens) == text
    assert len([t for t in tokens if "href" in t]) == 2
    assert "§ 1" in tokens[0]["text"] and "href" not in tokens[0]
    refs = [{"field": "body", "quote": "§ 1", "law_number": 555, "law_year": 2003, "section": "1"}]
    tokens = linked_text(text, refs, "body", "test & one")
    assert tokens[1]["href"] == "/laws/2003/555?test=test+%26+one&section=1"
    assert "href" not in linked_text("§ 1 a § 1", refs, "body", "test")[0]
    assert "href" not in linked_text("§ 2", refs, "body", "test")[0]
    assert "href" in linked_text("č. 190/2003", [], "body", "test")[0]
    assert "href" not in linked_text("termín 1/2026", [], "body", "test")[0]
    assert anchor_matches("paragraf-4.odsek-2.pismeno-j.text", "4", "2", "j")
    assert not anchor_matches("paragraf-40.odsek-2.pismeno-j.text", "4", "2", "j")
    assert not anchor_matches("paragraf-4.odsek-2.pismeno-i.text", "4", "2", "j")


@pytest.fixture(scope="module")
def reader():
    prepare()
    cfg = Settings.load()
    fixture = json.loads(MANIFEST.read_text())
    try:
        with TestClient(create_app(cfg)) as client:
            yield cfg, client, fixture
    finally:
        cleanup()


def test_public_reader_pins_date_and_exact_provision(reader):
    cfg, client, fixture = reader
    run = fixture["run_id"]
    question = client.get(f"/api/questions/{run}").json()
    assert any("section=4" in t.get("href", "") for t in question["linked_body"])
    assert any("letter=j" in t.get("href", "") for t in question["linked_answer"])
    route = f"/api/laws/2026/9998?test={run}"
    response = client.get(route + "&section=4&paragraph=2&letter=j")
    assert response.status_code == 200
    body = response.json()
    assert body["document_id"] == run
    assert body["version_id"] == fixture["version_id"]
    assert body["legal_date"] == "2026-06-01"
    assert body["effective_from"] == "2026-01-01"
    assert body["target_found"]
    highlighted = [p for p in body["provisions"] if p["highlighted"]]
    assert len(highlighted) == 1 and highlighted[0]["anchor"].endswith("pismeno-j.text")
    assert "FUTURE_VERSION" not in response.text
    assert client.get(route + "&section=4&paragraph=2&letter=z").json()["target_found"] is False
    assert client.get(route + "&paragraph=2").status_code == 422
    assert client.get(route + "&section=%3Cscript%3E").status_code == 422
    assert client.get("/api/laws/2003/190?test=firearms-sk-2026").status_code == 409
    assert client.get("/api/laws/2026/9998?test=hidden").status_code == 404
    assert client.get(route.replace("9998", "9997")).status_code == 404
    with connect(cfg.database_url) as conn:
        conn.execute("UPDATE test_definitions SET legal_date='2025-01-01' WHERE id=%s", (run,))
    assert client.get(route).status_code == 404  # No future/earliest-version fallback.
    with connect(cfg.database_url) as conn:
        conn.execute("UPDATE test_definitions SET legal_date='2026-06-01' WHERE id=%s", (run,))
    with TestClient(create_app(replace(cfg, laws_database_url=""))) as unavailable:
        assert unavailable.get(route).status_code == 503
    with TestClient(create_app(replace(cfg, environment="production"))) as production:
        assert production.get(route).status_code == 404


def test_expired_version_is_not_misrepresented(reader):
    cfg, client, fixture = reader
    with connect(cfg.laws_database_url) as conn:
        conn.execute(
            """INSERT INTO law_metadata(law_metadata_id,document_id,version_id,law_identifier_text,title,law_type,
          publication_date,effective_from,effective_to,legal_areas_json,metadata_json,created_at,updated_at)
          VALUES(%s,%s,%s,'9998/2026','synthetic','test','2026-01-01','2026-01-01','2026-05-31','[]','{}',now(),now())""",
            (fixture["run_id"], fixture["run_id"], fixture["version_id"]),
        )
    try:
        assert client.get(f"/api/laws/2026/9998?test={fixture['run_id']}").status_code == 404
    finally:
        with connect(cfg.laws_database_url) as conn:
            conn.execute("DELETE FROM law_metadata WHERE law_metadata_id=%s", (fixture["run_id"],))
