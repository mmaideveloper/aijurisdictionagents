"""Real PostgreSQL/identity authorization; model stubs are early regression evidence only."""

import io
import secrets
import shutil
from pathlib import Path
from uuid import uuid4

import pytest
from aijurisdictionagents.api_db import ApiDatabaseStore
from fastapi.testclient import TestClient
from PIL import Image

from laws_tests.app import create_app, digest
from laws_tests.config import Settings
from laws_tests.db import connect
from laws_tests.jobs import job_directory, merge_page, run_once


@pytest.fixture(scope="module")
def system():
    cfg = Settings.load()
    assert cfg.environment != "production"
    run = "private-unit-" + uuid4().hex
    store = ApiDatabaseStore(
        db_path=Path("unused"),
        blob_root=Path("runs/issue924/unit-blobs"),
        db_option="postgres",
        db_cloud=cfg.identity_database_url,
    )
    users = {}
    clients = {}
    for role in ("admin", "firearms", "medical", "both"):
        user = store.create_user(
            email=f"{run}-{role}@example.invalid",
            password=secrets.token_urlsafe(32),
            full_name="Synthetic bank unit",
        )
        if role == "admin":
            with connect(cfg.identity_database_url) as conn:
                conn.execute("UPDATE users SET role='admin' WHERE user_id=%s", (user.user_id,))
        token, csrf = uuid4().hex, uuid4().hex
        with connect(cfg.database_url) as conn:
            conn.execute(
                "INSERT INTO web_sessions VALUES(%s,%s,%s,now()+interval '1 hour')",
                (digest(token), user.user_id, csrf),
            )
        client = TestClient(create_app(cfg))
        client.cookies.set("laws_session", token)
        users[role] = user.user_id
        clients[role] = (client, {"origin": cfg.public_url, "x-csrf-token": csrf})
    banks = [run + "-firearms", run + "-medical"]
    with connect(cfg.database_url) as conn:
        for bank in banks:
            conn.execute(
                "INSERT INTO test_definitions(id,name,version,status,categories,exam_categories) VALUES(%s,'Synthetic bank','1','development','[\"A\"]','[\"A\"]')",
                (bank,),
            )
            for number in range(1, 4):
                conn.execute(
                    """INSERT INTO questions(id,test_id,category,number,title,body,answer,structure,tags)
                VALUES(%s,%s,'A',%s,'Synthetic water','What is the formula of water?','H2O','direct',%s)""",
                    (
                        f"{bank}-{number}",
                        bank,
                        number,
                        '["subject:biology","school-year:1"]'
                        if number == 1
                        else '["subject:chemistry","school-year:2"]',
                    ),
                )
    try:
        yield cfg, users, clients, banks
    finally:
        for client, _ in clients.values():
            client.close()
        with connect(cfg.database_url) as conn:
            jobs = conn.execute(
                "DELETE FROM bank_jobs WHERE test_id=ANY(%s) RETURNING id", (banks,)
            ).fetchall()
            for table in ("study_sets", "test_sessions", "bank_access"):
                conn.execute(f"DELETE FROM {table} WHERE test_id=ANY(%s)", (banks,))
            conn.execute(
                "DELETE FROM question_revisions WHERE question_id IN (SELECT id FROM questions WHERE test_id=ANY(%s))",
                (banks,),
            )
            conn.execute("DELETE FROM questions WHERE test_id=ANY(%s)", (banks,))
            conn.execute("DELETE FROM test_definitions WHERE id=ANY(%s)", (banks,))
            for uid in users.values():
                conn.execute("DELETE FROM test_users WHERE user_id=%s", (uid,))
                conn.execute("DELETE FROM web_sessions WHERE user_id=%s", (uid,))
                conn.execute("DELETE FROM bank_audit WHERE actor_id=%s", (uid,))
        for job in jobs:
            shutil.rmtree(job_directory(job["id"]), ignore_errors=True)
        with connect(cfg.identity_database_url) as conn:
            for uid in users.values():
                conn.execute("DELETE FROM users WHERE user_id=%s", (uid,))


def approve(system, role, banks, enabled=True):
    _, users, clients, _ = system
    client, headers = clients["admin"]
    response = client.put(
        "/api/admin/users/" + users[role],
        json={"approved": enabled, "bank_ids": banks},
        headers=headers,
    )
    assert response.status_code == 200, response.text


def test_approval_matrix_and_no_public_leaks(system):
    cfg, _, clients, banks = system
    with TestClient(create_app(cfg)) as visitor:
        assert (
            visitor.post(
                f"/api/admin/banks/{banks[0]}/imports",
                content=b"not a valid form",
                headers={"content-type": "multipart/form-data; boundary=broken"},
            ).status_code
            == 401
        )
        assert visitor.get("/api/tests").status_code == 200
        assert visitor.get(f"/api/questions/{banks[0]}-1").status_code == 401
        assert visitor.get(f"/api/tests/{banks[0]}/questions").status_code == 401
    for role, allowed in (("firearms", [banks[0]]), ("medical", [banks[1]]), ("both", banks)):
        client, headers = clients[role]
        assert client.get(f"/api/questions/{banks[0]}-1").status_code == 403
        assert client.post("/api/access-requests/" + allowed[0], headers=headers).status_code == 200
        assert client.get("/api/admin/users").status_code == 403
        assert (
            client.post(
                f"/api/admin/banks/{banks[0]}/imports",
                content=b"not a valid form",
                headers={"content-type": "multipart/form-data; boundary=broken"},
            ).status_code
            == 403
        )
        approve(system, role, allowed)
        for bank in banks:
            expected = 200 if bank in allowed else 403
            assert client.get(f"/api/questions/{bank}-1").status_code == expected
            assert client.get(f"/api/tests/{bank}/questions").status_code == expected
        assert client.get("/api/questions/lfuk-biology-imaginary").status_code == 404
        assert client.get("/api/tests/lfuk-biology/questions").status_code == 403


def test_collections_filters_revocation_and_disabled_questions(system):
    _, _, clients, banks = system
    approve(system, "firearms", [banks[0]])
    approve(system, "both", banks)
    client, headers = clients["firearms"]
    filtered = client.get(
        f"/api/tests/{banks[0]}/questions",
        params={"tags": "subject:biology,school-year:1,school-year:2"},
    ).json()
    assert [q["number"] for q in filtered] == [1]
    assert len(client.get(f"/api/tests/{banks[0]}/questions", params={"search": "H2O"}).json()) == 3
    body = {"test_id": banks[0], "name": "Synthetic year one", "question_ids": [banks[0] + "-1"]}
    sid = client.post("/api/study-sets", json=body, headers=headers).json()["id"]
    other, oh = clients["both"]
    assert other.put("/api/study-sets/" + sid, json=body, headers=oh).status_code == 404
    assert (
        client.post(
            "/api/study-sets", json={**body, "question_ids": [banks[1] + "-1"]}, headers=headers
        ).status_code
        == 409
    )
    session = client.post(
        "/api/sessions", json={"test_id": banks[0], "study_set_id": sid}, headers=headers
    ).json()
    assert session["question_ids"] == body["question_ids"]
    approve(system, "firearms", [])
    assert client.get("/api/sessions/" + session["id"] + "/result").status_code == 403
    assert client.get("/api/study-sets").json() == []
    assert (
        client.post(
            "/api/attempts",
            json={
                "session_id": session["id"],
                "question_id": banks[0] + "-1",
                "answer": "H2O",
                "request_id": str(uuid4()),
            },
            headers=headers,
        ).status_code
        == 403
    )
    approve(system, "firearms", [banks[0]])
    cfg = system[0]
    with connect(cfg.database_url) as conn:
        conn.execute("UPDATE questions SET enabled=false WHERE id=%s", (banks[0] + "-1",))
    try:
        assert client.get("/api/questions/" + banks[0] + "-1").status_code == 404
        assert (
            client.post(
                "/api/sessions", json={"test_id": banks[0], "study_set_id": sid}, headers=headers
            ).status_code
            == 409
        )
    finally:
        with connect(cfg.database_url) as conn:
            conn.execute("UPDATE questions SET enabled=true WHERE id=%s", (banks[0] + "-1",))


def test_revision_conflict_and_admin_csrf(system):
    cfg, _, clients, banks = system
    client, headers = clients["admin"]
    q = client.get(f"/api/admin/banks/{banks[0]}/questions").json()[0]
    keys = (
        "category",
        "number",
        "title",
        "body",
        "answer",
        "subquestions",
        "tags",
        "options",
        "related_ids",
        "enabled",
        "revision",
        "legal_references",
    )
    payload = {k: q[k] for k in keys}
    route = f"/api/admin/banks/{banks[0]}/questions/{q['id']}"
    assert client.put(route, json=payload).status_code == 403
    assert (
        client.put(
            route, json={**payload, "title": "Revised synthetic"}, headers=headers
        ).status_code
        == 200
    )
    assert client.put(route, json=payload, headers=headers).status_code == 409
    with connect(cfg.database_url) as conn:
        old = conn.execute(
            "SELECT snapshot FROM question_revisions WHERE question_id=%s AND revision=%s",
            (q["id"], q["revision"]),
        ).fetchone()
        assert old["snapshot"]["title"] == q["title"]


def test_reviewed_image_import_and_tag_undo(system, monkeypatch):
    cfg, _, clients, banks = system
    client, headers = clients["admin"]
    image = io.BytesIO()
    Image.new("RGB", (120, 120), "white").save(image, format="PNG")
    route = f"/api/admin/banks/{banks[1]}/imports"
    assert (
        client.post(
            route,
            files={"files": ("evil.txt", b"fake")},
            data={"authorized": "true"},
            headers=headers,
        ).status_code
        == 422
    )
    uploaded = client.post(
        route,
        files={"files": ("../../source.png", image.getvalue(), "image/png")},
        data={"authorized": "true"},
        headers=headers,
    )
    assert uploaded.status_code == 200, uploaded.text
    jid = uploaded.json()["id"]
    assert clients["medical"][0].get(f"/api/admin/jobs/{jid}/sources/0").status_code == 403
    record = {
        "category": "A",
        "number": 101,
        "title": "Synthetic imported",
        "body": "Formula of water?",
        "answer": "H2O",
        "subquestions": [],
        "options": [],
        "issues": [],
        "continuation": False,
    }
    monkeypatch.setattr("laws_tests.jobs.model_json", lambda *a, **kw: {"records": [record]})
    assert run_once(cfg)
    job = client.get("/api/admin/jobs/" + jid).json()
    assert job["status"] == "review"
    assert client.post(f"/api/admin/jobs/{jid}/apply", headers=headers).status_code == 422
    draft = {k: v for k, v in job["result"][0].items() if k != "issues"}
    assert (
        client.put(
            f"/api/admin/jobs/{jid}/review", json={"records": [draft]}, headers=headers
        ).status_code
        == 200
    )
    assert client.post(f"/api/admin/jobs/{jid}/apply", headers=headers).status_code == 200
    assert client.post(f"/api/admin/jobs/{jid}/apply", headers=headers).status_code == 409
    rows = client.get(f"/api/admin/banks/{banks[1]}/questions").json()
    imported = next(q for q in rows if q["number"] == 101)
    assert imported["enabled"] is False and imported["provenance"][0]["pages"] == [1]
    qid = imported["id"]
    tagjob = client.post(
        f"/api/admin/banks/{banks[1]}/tagging",
        json={
            "question_ids": [qid],
            "instruction": "Tag subject chemistry",
            "rubric": "Use subject:chemistry for chemical formula questions",
        },
        headers=headers,
    ).json()["id"]
    monkeypatch.setattr(
        "laws_tests.jobs.model_json",
        lambda *a, **kw: {
            "tags": ["subject:chemistry"],
            "rationale": "Synthetic rule",
            "uncertain": False,
        },
    )
    assert run_once(cfg)
    assert client.post(f"/api/admin/jobs/{tagjob}/apply", headers=headers).status_code == 200
    with connect(cfg.database_url) as conn:
        assert conn.execute("SELECT tags FROM questions WHERE id=%s", (qid,)).fetchone()[
            "tags"
        ] == ["subject:chemistry"]
    assert client.post(f"/api/admin/jobs/{tagjob}/undo", headers=headers).status_code == 200
    with connect(cfg.database_url) as conn:
        assert (
            conn.execute("SELECT tags FROM questions WHERE id=%s", (qid,)).fetchone()["tags"] == []
        )


def test_cancel_fences_running_worker(system, monkeypatch):
    cfg, _, clients, banks = system
    client, headers = clients["admin"]
    jid = client.post(
        f"/api/admin/banks/{banks[0]}/tagging",
        json={
            "question_ids": [banks[0] + "-1"],
            "instruction": "Classify chemistry",
            "rubric": "Use subject:chemistry only",
        },
        headers=headers,
    ).json()["id"]

    def cancelled(*args, **kwargs):
        assert client.post(f"/api/admin/jobs/{jid}/cancel", headers=headers).status_code == 200
        return {"tags": ["subject:chemistry"], "rationale": "synthetic", "uncertain": False}

    monkeypatch.setattr("laws_tests.jobs.model_json", cancelled)
    assert run_once(cfg)
    result = client.get("/api/admin/jobs/" + jid).json()
    assert result["status"] == "cancelled" and result["cursor"] == 0


def test_continuations_do_not_silently_pass_review():
    records = merge_page(
        [], [{"category": "A", "number": 1, "body": "Question", "answer": "First", "issues": []}], 1
    )
    merged = merge_page(
        records,
        [{"category": "A", "number": 1, "answer": "Second", "continuation": True, "issues": []}],
        2,
    )
    assert merged[0]["answer"] == "First\nSecond"
    assert merged[0]["source_pages"] == [1, 2] and merged[0]["issues"]


def test_scanned_pdf_renders_without_context_manager_assumptions(tmp_path, monkeypatch):
    from starlette.datastructures import UploadFile

    from laws_tests.jobs import page_input, store_sources

    monkeypatch.setattr("laws_tests.jobs.job_directory", lambda job_id: tmp_path / str(job_id))
    source = io.BytesIO()
    Image.new("RGB", (200, 300), "white").save(source, format="PDF")
    source.seek(0)
    jid = uuid4()
    files, total = store_sources(jid, [UploadFile(source, filename="scan.pdf")])
    text, image = page_input({"id": jid, "payload": files}, 0)
    assert total == 1 and text == "" and len(image) > 100


def test_import_rejects_excess_pages_and_disguised_images(tmp_path, monkeypatch):
    from starlette.datastructures import UploadFile

    from laws_tests.jobs import store_sources

    monkeypatch.setattr("laws_tests.jobs.job_directory", lambda job_id: tmp_path / str(job_id))
    image = Image.new("RGB", (30, 30), "white")
    pdf = io.BytesIO()
    image.save(pdf, format="PDF", save_all=True, append_images=[image] * 500)
    pdf.seek(0)
    with pytest.raises(ValueError, match="page_count"):
        store_sources(uuid4(), [UploadFile(pdf, filename="501-pages.pdf")])
    gif = io.BytesIO()
    image.save(gif, format="GIF")
    gif.seek(0)
    with pytest.raises(ValueError, match="image_format"):
        store_sources(uuid4(), [UploadFile(gif, filename="disguised.png")])


def test_untrusted_model_shapes_are_validated():
    with pytest.raises(ValueError):
        merge_page([], [{"category": "A", "number": 1, "issues": "not-an-array"}], 1)
    records = merge_page(
        [],
        [{"category": "A", "number": 1, "body": "Formula of water? Answer: H2O", "answer": "H2O"}],
        1,
    )
    assert records[0]["issues"] and records[0]["body"] == "Formula of water? Answer: H2O"


def test_global_approval_and_current_admin_role_are_authoritative(system):
    cfg, users, clients, banks = system
    approve(system, "both", banks, enabled=False)
    assert clients["both"][0].get("/api/questions/" + banks[0] + "-1").status_code == 403
    approve(system, "both", banks)
    with connect(cfg.identity_database_url) as conn:
        conn.execute("UPDATE users SET role='user' WHERE user_id=%s", (users["admin"],))
    try:
        assert clients["admin"][0].get("/api/admin/banks").status_code == 403
        assert clients["admin"][0].get("/api/me").json()["isAdmin"] is False
    finally:
        with connect(cfg.identity_database_url) as conn:
            conn.execute("UPDATE users SET role='admin' WHERE user_id=%s", (users["admin"],))
    future = banks[0] + "-future"
    with connect(cfg.database_url) as conn:
        conn.execute(
            "INSERT INTO test_definitions(id,name,version,status,categories) VALUES(%s,'Future synthetic','1','draft','[\"A\"]')",
            (future,),
        )
    try:
        assert clients["both"][0].get("/api/tests/" + future + "/questions").status_code == 403
    finally:
        with connect(cfg.database_url) as conn:
            conn.execute("DELETE FROM test_definitions WHERE id=%s", (future,))


def test_generic_publication_and_legal_scope(system):
    cfg, _, clients, banks = system
    client, headers = clients["admin"]
    bank = banks[0] + "-scope"
    payload = {
        "id": bank,
        "name": "Synthetic mathematics",
        "subject": "mathematics",
        "categories": ["A"],
        "status": "draft",
    }
    try:
        assert (
            client.put("/api/admin/banks/" + bank, json=payload, headers=headers).status_code == 200
        )
        assert (
            client.post(
                f"/api/admin/banks/{bank}/questions",
                headers=headers,
                json={
                    "category": "A",
                    "number": 1,
                    "title": "Synthetic arithmetic",
                    "body": "One plus one?",
                    "answer": "Two",
                },
            ).status_code
            == 200
        )
        published = {
            **payload,
            "status": "published",
            "rights_confirmed": True,
            "source_links": ["https://example.invalid/original-synthetic"],
        }
        # Non-legal subjects need no invented legal reference date.
        assert (
            client.put("/api/admin/banks/" + bank, json=published, headers=headers).status_code
            == 200
        )
        assert (
            client.put(
                "/api/admin/banks/" + bank,
                json={**published, "requires_legal_date": True},
                headers=headers,
            ).status_code
            == 422
        )
        assert (
            client.put(
                "/api/admin/banks/" + bank,
                json={**published, "requires_legal_date": True, "legal_date": "2026-10-18"},
                headers=headers,
            ).status_code
            == 200
        )
        # New banks cannot evade review by selecting the legacy preview state.
        assert (
            client.put(
                "/api/admin/banks/" + bank, json={**payload, "status": "preview"}, headers=headers
            ).status_code
            == 409
        )
    finally:
        with connect(cfg.database_url) as conn:
            conn.execute("DELETE FROM questions WHERE test_id=%s", (bank,))
            conn.execute("DELETE FROM test_definitions WHERE id=%s", (bank,))


def test_bulk_status_is_versioned_atomic_and_bank_scoped(system):
    _, _, clients, banks = system
    client, headers = clients["admin"]
    rows = client.get(f"/api/admin/banks/{banks[0]}/questions").json()
    selected = [{"id": q["id"], "revision": q["revision"]} for q in rows]
    route = f"/api/admin/banks/{banks[0]}/question-status"
    assert (
        client.post(
            route, headers=headers, json={"questions": selected, "enabled": False}
        ).status_code
        == 200
    )
    assert all(
        not q["enabled"] for q in client.get(f"/api/admin/banks/{banks[0]}/questions").json()
    )
    assert (
        client.post(
            route, headers=headers, json={"questions": selected, "enabled": True}
        ).status_code
        == 409
    )
    rows = client.get(f"/api/admin/banks/{banks[0]}/questions").json()
    selected = [{"id": q["id"], "revision": q["revision"]} for q in rows]
    assert (
        client.post(
            route, headers=headers, json={"questions": selected, "enabled": True}
        ).status_code
        == 200
    )
    foreign = client.get(f"/api/admin/banks/{banks[1]}/questions").json()[0]
    assert (
        client.post(
            route,
            headers=headers,
            json={
                "questions": [{"id": foreign["id"], "revision": foreign["revision"]}],
                "enabled": False,
            },
        ).status_code
        == 404
    )
