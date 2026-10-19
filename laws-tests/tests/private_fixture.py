"""Unique synthetic private-bank E2E records; credentials stay in an ignored local file."""

import json
import secrets
import shutil
import sys
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

from aijurisdictionagents.api_db import ApiDatabaseStore
from dotenv import set_key
from PIL import Image, ImageDraw, ImageFont

from laws_tests.config import Settings
from laws_tests.db import connect
from laws_tests.jobs import job_directory

ROOT = Path(__file__).resolve().parents[2]
PRIVATE = ROOT / "runs/issue924/private-fixture.json"


def cleanup():
    bootstrap = ROOT / "runs/issue924/synthetic-account.json"
    if bootstrap.exists():
        cfg = Settings.load()
        assert cfg.environment == "development"
        seed = json.loads(bootstrap.read_text(encoding="utf-8"))
        if seed["email"] != "laws-tests-924@example.invalid":
            raise ValueError("Refusing non-synthetic bootstrap cleanup")
        with connect(cfg.database_url) as conn:
            for table in (
                "test_sessions",
                "web_sessions",
                "login_requests",
                "study_sets",
                "test_users",
            ):
                conn.execute(f"DELETE FROM {table} WHERE user_id=%s", (seed["user_id"],))
        with connect(cfg.identity_database_url) as conn:
            conn.execute(
                "DELETE FROM users WHERE user_id=%s AND email=%s", (seed["user_id"], seed["email"])
            )
        bootstrap.unlink()
    if not PRIVATE.exists():
        return
    record = json.loads(PRIVATE.read_text(encoding="utf-8"))
    cfg = Settings.load()
    assert cfg.environment != "production" and record["run"].startswith("private-924-")
    banks = record["banks"]
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
        for user in record["users"].values():
            for table in ("test_users", "web_sessions", "login_requests"):
                conn.execute(f"DELETE FROM {table} WHERE user_id=%s", (user["user_id"],))
            conn.execute("DELETE FROM bank_audit WHERE actor_id=%s", (user["user_id"],))
    for job in jobs:
        shutil.rmtree(job_directory(job["id"]), ignore_errors=True)
    with connect(cfg.identity_database_url) as conn:
        for user in record["users"].values():
            if conn.execute("SELECT to_regclass('email_outbox') AS table_name").fetchone()[
                "table_name"
            ]:
                conn.execute("DELETE FROM email_outbox WHERE recipient=%s", (user["email"],))
            conn.execute(
                "DELETE FROM users WHERE user_id=%s AND email=%s", (user["user_id"], user["email"])
            )
    PRIVATE.unlink()
    manifest_path = ROOT / "runs/issue924/evidence/result-manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("runId") == record["run"]:
            manifest["syntheticRecordsCleaned"] = True
            manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    for filename in ("source.png", "source.jpeg", "source.pdf", "text.pdf"):
        (ROOT / "runs/issue924" / filename).unlink(missing_ok=True)
    print("Private-bank synthetic records and credentials removed.")


def prepare():
    cleanup()
    cfg = Settings.load()
    assert cfg.environment == "development"
    run = "private-924-" + uuid4().hex
    directory = ROOT / "runs/issue924"
    directory.mkdir(parents=True, exist_ok=True)
    store = ApiDatabaseStore(
        db_path=directory / "unused",
        blob_root=directory / "blobs",
        db_option="postgres",
        db_cloud=cfg.identity_database_url,
    )
    record = {
        "run": run,
        "banks": [run + "-firearms", run + "-medical"],
        "users": {},
        "databasePort": urlsplit(cfg.database_url).port,
    }
    for role in ("admin", "firearms", "medical", "both"):
        email = f"{run}-{role}@example.invalid"
        user = store.create_user(
            email=email,
            password=secrets.token_urlsafe(32),
            full_name="Synthetic private bank learner",
        )
        if role == "admin":
            with connect(cfg.identity_database_url) as conn:
                conn.execute("UPDATE users SET role='admin' WHERE user_id=%s", (user.user_id,))
        device = str(uuid4())
        token = store.issue_device_auth_token(
            user_id=user.user_id, device_id=device, expires_in_days=1
        )
        record["users"][role] = {
            "user_id": user.user_id,
            "email": email,
            "device_id": device,
            "device_token": token,
        }
        PRIVATE.write_text(json.dumps(record), encoding="utf-8")
    with connect(cfg.database_url) as conn:
        for bank, kind in zip(record["banks"], ("Firearms", "Medical"), strict=True):
            category = "A" if kind == "Firearms" else "biology"
            conn.execute(
                """INSERT INTO test_definitions(id,name,version,status,categories,exam_categories,description)
                VALUES(%s,%s,'synthetic-924','development',%s,%s,'Original synthetic acceptance content, not purchased book content.')""",
                (
                    bank,
                    "Synthetic " + kind + " 924",
                    json.dumps([category]),
                    json.dumps([category]),
                ),
            )
            conn.execute(
                """INSERT INTO questions(id,test_id,category,number,title,body,answer,structure,tags)
                VALUES(%s,%s,%s,1,'Water formula','What is the chemical formula of water?','H2O','direct','["subject:chemistry","school-year:1"]')""",
                (bank + "-1", bank, category),
            )
    try:
        font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 32)
    except OSError:
        font = ImageFont.load_default(size=32)
    for number, extension in ((101, "png"), (102, "jpeg"), (103, "pdf")):
        image = Image.new("RGB", (1400, 900), "white")
        draw = ImageDraw.Draw(image)
        draw.multiline_text(
            (75, 70),
            f"Original synthetic study page\nCategory: biology\nQuestion {number}\nWater molecule\nWhat is the chemical formula of water?\nAnswer: H2O\n",
            font=font,
            fill="black",
            spacing=25,
        )
        image.save(directory / f"source.{extension}")
    # A true text PDF checks text extraction as well as the scanned-PDF vision route.
    from reportlab.pdfgen import canvas

    pdf = canvas.Canvas(str(directory / "text.pdf"))
    pdf.drawString(50, 780, "Original synthetic study page. Category biology. Question 104.")
    pdf.drawString(50, 750, "Water molecule: What is the chemical formula of water?")
    pdf.drawString(50, 720, "Answer: H2O")
    pdf.save()
    import pypdfium2 as pdfium
    from pypdf import PdfReader

    evidence = directory / "evidence"
    evidence.mkdir(exist_ok=True)
    for filename in ("source.pdf", "text.pdf"):
        source = directory / filename
        reader = PdfReader(source)
        assert len(reader.pages) == 1
        if filename == "text.pdf":
            assert "H2O" in reader.pages[0].extract_text()
        shutil.copyfile(source, evidence / filename)
        with pdfium.PdfDocument(source) as document:
            page = document[0]
            bitmap = page.render(scale=1)
            bitmap.to_pil().save(evidence / (filename + ".png"))
            bitmap.close()
            page.close()
    set_key(ROOT / ".env-laws-test", "LAWS_TEST_PUBLIC_URL", "http://127.0.0.1:8940")
    print("Private-bank synthetic fixture ready. Credentials withheld.")


if __name__ == "__main__":
    cleanup() if len(sys.argv) > 1 and sys.argv[1] == "cleanup" else prepare()
