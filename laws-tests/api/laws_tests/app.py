from contextlib import asynccontextmanager
from datetime import datetime, timezone
from hashlib import sha256
import secrets
from urllib.parse import urlencode
from uuid import UUID, uuid4

from fastapi import FastAPI, HTTPException, Request, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, JSONResponse
from pydantic import BaseModel, Field
from psycopg.types.json import Jsonb

from .config import Settings
from .db import connect, purge
from .evaluation import evaluate
from .identity import Identity
from .legal import enrich_question, read_law


def digest(value: str) -> str:
    return sha256(value.encode()).hexdigest()


class Authorization(BaseModel):
    state: str = Field(min_length=32, max_length=128)
    user_id: str
    device_id: str
    device_token: str


class SessionInput(BaseModel):
    test_id: str
    mode: str = "learning"
    question_id: str | None = None


class AnswerInput(BaseModel):
    session_id: UUID
    question_id: str
    subquestion_id: str | None = None
    answer: str = Field(min_length=1, max_length=12000)
    request_id: UUID


def create_app(settings: Settings | None = None) -> FastAPI:
    cfg = settings or Settings.load()
    identity = Identity(cfg.identity_database_url)

    @asynccontextmanager
    async def lifespan(app):
        with connect(cfg.database_url) as conn:
            purge(conn)
        yield

    app = FastAPI(title="JurisDigta Laws Tests", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[cfg.auth_origin],
        allow_methods=["POST"],
        allow_headers=["Content-Type"],
    )

    @app.middleware("http")
    async def privacy_headers(request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    def public_test(conn, test_id):
        row = conn.execute("SELECT * FROM test_definitions WHERE id=%s", (test_id,)).fetchone()
        if not row or row["status"] not in (
            ["published"] if cfg.environment == "production" else ["published", "development"]
        ):
            raise HTTPException(404, "Test nie je dostupný.")
        return row

    def active(row):
        if row["expires_at"] and row["expires_at"] <= datetime.now(timezone.utc):
            raise HTTPException(409, "Platnosť testu skončila. Obsah a história sú dostupné iba na čítanie.")

    def session_user(request, conn, mutation=False):
        token = request.cookies.get("laws_session", "")
        row = conn.execute(
            "SELECT * FROM web_sessions WHERE token_hash=%s AND expires_at>now()", (digest(token),)
        ).fetchone()
        if not row:
            raise HTTPException(401, "Najprv sa prihláste cez JurisDigta.")
        user = identity.find_user_by_id(user_id=row["user_id"])
        if not user or not user.is_enabled:
            conn.execute("DELETE FROM web_sessions WHERE user_id=%s", (row["user_id"],))
            if not user:
                conn.execute("DELETE FROM test_sessions WHERE user_id=%s", (row["user_id"],))
            conn.commit()
            raise HTTPException(401, "Účet nie je dostupný.")
        if mutation:
            if request.headers.get("origin") != cfg.public_url.rstrip("/"):
                raise HTTPException(403, "Invalid origin")
            if not secrets.compare_digest(request.headers.get("x-csrf-token", ""), row["csrf"]):
                raise HTTPException(403, "Invalid request token")
        return row

    @app.get("/api/health")
    def health():
        with connect(cfg.database_url) as conn:
            conn.execute("SELECT 1 FROM test_definitions LIMIT 1")
        return {"status": "ok", "service": "laws-tests"}

    @app.get("/api/config")
    def public_config():
        return {"authOrigin": cfg.auth_origin, "development": cfg.environment != "production"}

    @app.get("/api/auth/start")
    def auth_start(return_path: str = "/"):
        if not return_path.startswith("/") or return_path.startswith("//") or "\\" in return_path:
            raise HTTPException(400, "Invalid return path")
        state, browser = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        with connect(cfg.database_url) as conn:
            purge(conn)
            conn.execute(
                "INSERT INTO login_requests(state_hash,browser_hash,return_path,expires_at) VALUES(%s,%s,%s,now()+interval '5 minutes')",
                (digest(state), digest(browser), return_path),
            )
        response = RedirectResponse(cfg.auth_url + "?" + urlencode({"state": state}), status_code=303)
        response.set_cookie(
            "laws_login",
            browser,
            max_age=300,
            httponly=True,
            secure=cfg.environment == "production",
            samesite="lax",
            path="/api/auth",
        )
        return response

    @app.post("/api/auth/authorize")
    def authorize(payload: Authorization, request: Request):
        if request.headers.get("origin") != cfg.auth_origin:
            raise HTTPException(403, "Invalid authorization origin")
        user = identity.authenticate_user_device_auth_token(
            user_id=payload.user_id, device_id=payload.device_id, token=payload.device_token
        )
        if not user or not user.is_enabled:
            raise HTTPException(401, "Prihlásenie nie je platné.")
        code = secrets.token_urlsafe(32)
        with connect(cfg.database_url) as conn:
            changed = conn.execute(
                "UPDATE login_requests SET user_id=%s,code_hash=%s WHERE state_hash=%s AND expires_at>now() AND code_hash IS NULL RETURNING state_hash",
                (user.user_id, digest(code), digest(payload.state)),
            ).fetchone()
            if not changed:
                raise HTTPException(400, "Prihlásenie vypršalo alebo už bolo použité.")
        return {
            "redirect": cfg.public_url
            + "/api/auth/callback?"
            + urlencode({"code": code, "state": payload.state})
        }

    @app.get("/api/auth/callback")
    def callback(request: Request, code: str, state: str):
        with connect(cfg.database_url) as conn:
            row = conn.execute(
                "DELETE FROM login_requests WHERE state_hash=%s AND code_hash=%s AND browser_hash=%s AND expires_at>now() RETURNING *",
                (digest(state), digest(code), digest(request.cookies.get("laws_login", ""))),
            ).fetchone()
            if not row or not row["user_id"]:
                raise HTTPException(400, "Prihlásenie vypršalo alebo už bolo použité.")
            token = secrets.token_urlsafe(40)
            conn.execute(
                "INSERT INTO web_sessions VALUES(%s,%s,%s,now()+interval '12 hours')",
                (digest(token), row["user_id"], secrets.token_urlsafe(32)),
            )
        response = RedirectResponse(cfg.public_url + row["return_path"], status_code=303)
        response.set_cookie(
            "laws_session",
            token,
            max_age=43200,
            httponly=True,
            secure=cfg.environment == "production",
            samesite="lax",
        )
        response.delete_cookie("laws_login", path="/api/auth")
        return response

    @app.get("/api/me")
    def me(request: Request):
        with connect(cfg.database_url) as conn:
            row = session_user(request, conn)
            return {"signedIn": True, "csrf": row["csrf"]}

    @app.post("/api/logout")
    def logout(request: Request):
        with connect(cfg.database_url) as conn:
            session_user(request, conn, True)
            conn.execute(
                "DELETE FROM web_sessions WHERE token_hash=%s",
                (digest(request.cookies.get("laws_session", "")),),
            )
        response = JSONResponse({"status": "signed_out"})
        response.delete_cookie("laws_session")
        return response

    @app.get("/api/tests")
    def catalogue():
        with connect(cfg.database_url) as conn:
            statuses = ["published"] if cfg.environment == "production" else ["published", "development"]
            return conn.execute(
                "SELECT id,name,version,legal_date,status,expires_at,categories,exam_categories,aggregation,source_links,category_labels,legal_summary,case_type,(expires_at<=now()) AS expired FROM test_definitions WHERE status=ANY(%s) ORDER BY name",
                (statuses,),
            ).fetchall()

    @app.get("/api/tests/{test_id}/questions")
    def questions(test_id: str):
        with connect(cfg.database_url) as conn:
            public_test(conn, test_id)
            return conn.execute(
                "SELECT id,category,number,title,body,structure FROM questions WHERE test_id=%s ORDER BY category,number",
                (test_id,),
            ).fetchall()

    @app.get("/api/questions/{question_id}")
    def question(question_id: str):
        with connect(cfg.database_url) as conn:
            row = conn.execute(
                "SELECT id,test_id,category,number,title,body,structure,answer,provenance,legal_references FROM questions WHERE id=%s",
                (question_id,),
            ).fetchone()
            if not row:
                raise HTTPException(404)
            public_test(conn, row["test_id"])
            row["subquestions"] = conn.execute(
                "SELECT id,sequence,body,answer,legal_references FROM subquestions WHERE question_id=%s ORDER BY sequence",
                (question_id,),
            ).fetchall()
            return enrich_question(row)

    @app.get("/api/laws/{year}/{number}")
    def public_law(
        year: int,
        number: int,
        test: str,
        section: str | None = Query(None, pattern=r"^[0-9]{1,4}[a-z]?$"),
        paragraph: str | None = Query(None, pattern=r"^[0-9]{1,3}$"),
        letter: str | None = Query(None, pattern=r"^[a-z]$"),
    ):
        if not 1800 <= year <= 2100 or not 1 <= number <= 9999:
            raise HTTPException(422, "Neplatné číslo predpisu.")
        if (paragraph and not section) or (letter and not paragraph):
            raise HTTPException(422, "Neúplný odkaz na ustanovenie.")
        with connect(cfg.database_url) as conn:
            course = public_test(conn, test)
        return read_law(cfg.laws_database_url, year, number, course["legal_date"], section, paragraph, letter)

    @app.post("/api/sessions")
    def start_session(payload: SessionInput, request: Request):
        if payload.mode not in {"learning", "exam"}:
            raise HTTPException(422, "Invalid mode")
        with connect(cfg.database_url) as conn:
            user = session_user(request, conn, True)
            purge(conn)
            test = public_test(conn, payload.test_id)
            active(test)
            candidates = conn.execute(
                """SELECT q.id,q.category,avg(a.score) AS score,
                count(DISTINCT coalesce(a.subquestion_id,a.question_id)) AS answered_items,
                (SELECT greatest(count(*),1) FROM subquestions s WHERE s.question_id=q.id) AS required_items
                FROM questions q LEFT JOIN attempts a ON a.question_id=q.id AND a.user_id=%s AND a.status='completed'
                WHERE q.test_id=%s GROUP BY q.id""",
                (user["user_id"], payload.test_id),
            ).fetchall()

            def priority(q):
                score = float(q["score"] or 0)
                return (
                    0
                    if q["answered_items"] < q["required_items"]
                    else 1
                    if score < 70
                    else 2
                    if score < 85
                    else 3
                    if score < 95
                    else 4
                )

            secrets.SystemRandom().shuffle(candidates)
            candidates.sort(key=priority)
            if payload.mode == "exam":
                selected = []
                for category in test["exam_categories"]:
                    matches = [q for q in candidates if q["category"] == category]
                    if not matches:
                        raise HTTPException(
                            409, "Skúška nie je dostupná: chýba schválená otázka v kategórii."
                        )
                    selected.append(matches[0]["id"])
                if not selected:
                    raise HTTPException(409, "Skúška nie je nakonfigurovaná.")
            elif payload.question_id:
                selected = [q["id"] for q in candidates if q["id"] == payload.question_id]
            else:
                selected = [candidates[0]["id"]] if candidates else []
            if not selected:
                raise HTTPException(404)
            sid = uuid4()
            conn.execute(
                "INSERT INTO test_sessions(id,user_id,test_id,mode,question_ids) VALUES(%s,%s,%s,%s,%s)",
                (sid, user["user_id"], payload.test_id, payload.mode, Jsonb(selected)),
            )
            return {"id": str(sid), "question_ids": selected, "mode": payload.mode}

    @app.post("/api/attempts")
    def submit(payload: AnswerInput, request: Request):
        if not payload.answer.strip():
            raise HTTPException(422, "Napíšte odpoveď.")
        with connect(cfg.database_url) as conn:
            user = session_user(request, conn, True)
            purge(conn)
            session = conn.execute(
                "SELECT * FROM test_sessions WHERE id=%s AND user_id=%s",
                (payload.session_id, user["user_id"]),
            ).fetchone()
            if not session or payload.question_id not in session["question_ids"]:
                raise HTTPException(404)
            test = public_test(conn, session["test_id"])
            active(test)
            previous = conn.execute(
                "SELECT * FROM attempts WHERE user_id=%s AND request_id=%s",
                (user["user_id"], payload.request_id),
            ).fetchone()
            if previous:
                if (
                    previous["session_id"] != payload.session_id
                    or previous["question_id"] != payload.question_id
                    or previous["subquestion_id"] != payload.subquestion_id
                    or previous["user_answer"] != payload.answer
                ):
                    raise HTTPException(409, "Request ID already used")
                return previous
            parent = conn.execute("SELECT * FROM questions WHERE id=%s", (payload.question_id,)).fetchone()
            if parent["structure"] == "direct" and payload.subquestion_id is None:
                item = parent
            elif parent["structure"] == "grouped" and payload.subquestion_id:
                item = conn.execute(
                    "SELECT * FROM subquestions WHERE id=%s AND question_id=%s",
                    (payload.subquestion_id, payload.question_id),
                ).fetchone()
            else:
                item = None
            if not item:
                raise HTTPException(422, "Vyberte otázku s odpoveďou alebo podotázku.")
            snapshot = {key: item[key] for key in ("body", "answer", "rules")}
            snapshot["version"] = test["version"]
            aid = uuid4()
            inserted = conn.execute(
                """INSERT INTO attempts(id,user_id,test_id,session_id,question_id,subquestion_id,
                request_id,content_snapshot,user_answer,status,provider,model)
                VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,'pending','azurefoundry',%s)
                ON CONFLICT(user_id,request_id) DO NOTHING RETURNING id""",
                (
                    aid,
                    user["user_id"],
                    session["test_id"],
                    payload.session_id,
                    payload.question_id,
                    payload.subquestion_id,
                    payload.request_id,
                    Jsonb(snapshot),
                    payload.answer,
                    cfg.deployment,
                ),
            ).fetchone()
            if not inserted:
                raise HTTPException(409, "Odpoveď sa už spracúva.")
        try:
            result = evaluate(cfg, snapshot, payload.answer)
        except Exception:
            with connect(cfg.database_url) as conn:
                conn.execute("UPDATE attempts SET status='error' WHERE id=%s", (aid,))
            raise HTTPException(
                502, "Vyhodnotenie sa nepodarilo. Odpoveď je uložená bez skóre; môžete skúsiť nový pokus."
            ) from None
        with connect(cfg.database_url) as conn:
            # Deletion during evaluation must not resurrect an answer.
            record = conn.execute(
                """UPDATE attempts SET status='completed',score=%s,passed=%s,result=%s,evaluated_at=now()
                WHERE id=%s RETURNING *""",
                (result.score, result.score >= 70, Jsonb(result.model_dump()), aid),
            ).fetchone()
            if not record:
                raise HTTPException(410, "Pokus bol odstránený.")
            return record

    @app.get("/api/history")
    def history(request: Request):
        with connect(cfg.database_url) as conn:
            user = session_user(request, conn)
            purge(conn)
            return conn.execute(
                "SELECT * FROM attempts WHERE user_id=%s ORDER BY created_at DESC LIMIT 500",
                (user["user_id"],),
            ).fetchall()

    @app.get("/api/export")
    def export(request: Request):
        with connect(cfg.database_url) as conn:
            user = session_user(request, conn)
            purge(conn)
            return conn.execute(
                "SELECT * FROM attempts WHERE user_id=%s ORDER BY created_at", (user["user_id"],)
            ).fetchall()

    @app.get("/api/progress")
    def progress(request: Request):
        with connect(cfg.database_url) as conn:
            user = session_user(request, conn)
            purge(conn)
            return conn.execute(
                """WITH latest AS (
                  SELECT DISTINCT ON (question_id,subquestion_id) question_id,subquestion_id,score
                  FROM attempts WHERE user_id=%s AND status='completed'
                  ORDER BY question_id,subquestion_id,created_at DESC,id DESC
                )
                SELECT q.test_id,q.category,count(*)::int AS total,
                  count(l.score)::int AS answered,
                  count(*) FILTER(WHERE l.score>=70)::int AS passed,
                  count(*) FILTER(WHERE l.score>=95)::int AS mastered
                FROM questions q LEFT JOIN subquestions s ON s.question_id=q.id
                LEFT JOIN latest l ON l.question_id=q.id AND l.subquestion_id IS NOT DISTINCT FROM s.id
                GROUP BY q.test_id,q.category ORDER BY q.test_id,q.category""",
                (user["user_id"],),
            ).fetchall()

    @app.delete("/api/history")
    def delete_history(request: Request):
        with connect(cfg.database_url) as conn:
            user = session_user(request, conn, True)
            conn.execute("DELETE FROM test_sessions WHERE user_id=%s", (user["user_id"],))
        return {"status": "deleted"}

    @app.get("/api/sessions/{session_id}/result")
    def session_result(session_id: UUID, request: Request):
        with connect(cfg.database_url) as conn:
            user = session_user(request, conn)
            purge(conn)
            session = conn.execute(
                "SELECT * FROM test_sessions WHERE id=%s AND user_id=%s", (session_id, user["user_id"])
            ).fetchone()
            if not session:
                raise HTTPException(404)
            test = public_test(conn, session["test_id"])
            values = []
            for qid in session["question_ids"]:
                subs = conn.execute(
                    "SELECT id FROM subquestions WHERE question_id=%s ORDER BY sequence", (qid,)
                ).fetchall()
                scores = []
                for sub in subs or [{"id": None}]:
                    attempt = conn.execute(
                        "SELECT score FROM attempts WHERE session_id=%s AND question_id=%s AND subquestion_id IS NOT DISTINCT FROM %s AND status='completed' ORDER BY created_at DESC LIMIT 1",
                        (session_id, qid, sub["id"]),
                    ).fetchone()
                    if not attempt:
                        return {"complete": False}
                    scores.append(attempt["score"])
                values.append(min(scores) if test["aggregation"] == "minimum" else sum(scores) / len(scores))
            score = min(values) if test["aggregation"] == "minimum" else sum(values) / len(values)
            return {"complete": True, "score": round(score, 1), "passed": score >= 70}

    return app
