"""Tests-only administration and private study collections."""

import shutil
from datetime import date, datetime
from typing import Annotated, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from psycopg.errors import IntegrityError
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .access import audit, require_bank
from .db import connect


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Grant(Input):
    approved: bool
    bank_ids: list[str] = Field(max_length=100)


class Bank(Input):
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,79}$")
    name: str = Field(min_length=1, max_length=200)
    version: str = Field(default="1", max_length=40)
    description: str = Field(default="", max_length=4000)
    subject: str = Field(default="", max_length=100)
    categories: list[str] = Field(min_length=1, max_length=30)
    bank_tags: list[str] = Field(default_factory=list, max_length=100)
    exam_categories: list[str] = Field(default_factory=list, max_length=30)
    starts_at: datetime | None = None
    expires_at: datetime | None = None
    status: Literal["draft", "published", "withdrawn", "preview", "development"] = "draft"
    rights_confirmed: bool = False
    source_links: list[str] = Field(default_factory=list, max_length=30)
    legal_date: date | None = None
    requires_legal_date: bool = False

    @model_validator(mode="after")
    def dates(self):
        for value in (self.starts_at, self.expires_at):
            if value and value.tzinfo is None:
                raise ValueError("Dates must include a time zone")
        if self.starts_at and self.expires_at and self.starts_at >= self.expires_at:
            raise ValueError("Expiry must follow start")
        if not set(self.exam_categories).issubset(self.categories):
            raise ValueError("Exam categories must be bank categories")
        if self.status == "published" and (not self.rights_confirmed or not self.source_links):
            raise ValueError("Publication requires confirmed rights and source references")
        if self.status == "published" and self.requires_legal_date and not self.legal_date:
            raise ValueError("Legal banks require an effective legal date")
        return self


class Subquestion(Input):
    id: str = Field(default="", max_length=160)
    body: str = Field(min_length=1, max_length=20000)
    answer: str = Field(min_length=1, max_length=30000)


class QuestionInput(Input):
    category: str = Field(min_length=1, max_length=80)
    number: int = Field(gt=0)
    title: str = Field(min_length=1, max_length=400)
    body: str = Field(min_length=1, max_length=20000)
    answer: str | None = Field(default=None, max_length=30000)
    subquestions: list[Subquestion] = Field(default_factory=list, max_length=100)
    tags: list[str] = Field(default_factory=list, max_length=100)
    options: list[str] = Field(default_factory=list, max_length=30)
    related_ids: list[str] = Field(default_factory=list, max_length=30)
    enabled: bool = True
    revision: int = Field(default=1, ge=1)
    source_pages: list[int] = Field(default_factory=list, max_length=500)
    legal_references: list[dict] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def structure(self):
        if bool(self.subquestions) == bool(self.answer and self.answer.strip()):
            raise ValueError("Use a direct answer OR subquestions, never both/neither")
        if not self.body.strip() or not self.title.strip():
            raise ValueError("Question text is required")
        if any(not t.strip() or len(t) > 100 for t in self.tags):
            raise ValueError("Tags must contain 1..100 characters")
        return self


class Collection(Input):
    test_id: str
    name: str = Field(min_length=1, max_length=120)
    question_ids: list[str] = Field(min_length=1, max_length=2000)


class QuestionVersion(Input):
    id: str = Field(min_length=1, max_length=160)
    revision: int = Field(ge=1)


class StatusBatch(Input):
    questions: list[QuestionVersion] = Field(min_length=1, max_length=2000)
    enabled: bool


class TagRequest(Input):
    question_ids: list[str] = Field(min_length=1, max_length=2000)
    instruction: str = Field(min_length=5, max_length=4000)
    rubric: str = Field(min_length=5, max_length=8000)


class Review(Input):
    records: list[QuestionInput] = Field(min_length=1, max_length=3000)


def save_question(conn, bank_id, payload: QuestionInput, actor, question_id=None, provenance=None):
    bank = conn.execute("SELECT * FROM test_definitions WHERE id=%s FOR UPDATE", (bank_id,)).fetchone()
    if not bank or payload.category not in bank["categories"]:
        raise HTTPException(422, "Vyberte existujúcu kategóriu banky.")
    for related_id in payload.related_ids:
        if not conn.execute(
            "SELECT 1 FROM questions WHERE id=%s AND test_id=%s", (related_id, bank_id)
        ).fetchone():
            raise HTTPException(422, "Súvisiaca otázka musí patriť do rovnakej banky.")
    old = None
    if question_id:
        old = conn.execute(
            "SELECT * FROM questions WHERE id=%s AND test_id=%s FOR UPDATE", (question_id, bank_id)
        ).fetchone()
        if not old:
            raise HTTPException(404)
        if old["revision"] != payload.revision:
            raise HTTPException(409, "Otázku už niekto upravil. Obnovte stránku.")
        subs = conn.execute(
            "SELECT * FROM subquestions WHERE question_id=%s ORDER BY sequence", (question_id,)
        ).fetchall()
        if bool(subs) != bool(payload.subquestions) or [s["id"] for s in subs] != [
            s.id for s in payload.subquestions
        ]:
            raise HTTPException(409, "Existujúcu štruktúru a identifikátory podotázok zachovajte.")
        old["subquestions"] = subs
        conn.execute(
            "INSERT INTO question_revisions(question_id,revision,snapshot,actor_id) VALUES(%s,%s,%s,%s)",
            (question_id, old["revision"], Jsonb(old), actor),
        )
    qid = question_id or f"{bank_id}-{uuid4().hex}"
    values = (
        payload.category,
        payload.number,
        payload.title,
        payload.body,
        payload.answer,
        Jsonb(sorted(set(payload.tags))),
        Jsonb(payload.options),
        Jsonb(payload.related_ids),
        payload.enabled,
        Jsonb(payload.legal_references),
    )
    if old:
        conn.execute(
            """UPDATE questions SET category=%s,number=%s,title=%s,body=%s,answer=%s,
                     tags=%s,options=%s,related_ids=%s,enabled=%s,legal_references=%s,revision=revision+1 WHERE id=%s""",
            (*values, qid),
        )
        for sub in payload.subquestions:
            conn.execute(
                "UPDATE subquestions SET body=%s,answer=%s WHERE id=%s AND question_id=%s",
                (sub.body, sub.answer, sub.id, qid),
            )
    else:
        conn.execute(
            """INSERT INTO questions(category,number,title,body,answer,tags,options,related_ids,enabled,
                     legal_references,id,test_id,structure,provenance) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (*values, qid, bank_id, "grouped" if payload.subquestions else "direct", Jsonb(provenance or [])),
        )
        for sequence, sub in enumerate(payload.subquestions, 1):
            conn.execute(
                "INSERT INTO subquestions(id,question_id,sequence,body,answer) VALUES(%s,%s,%s,%s,%s)",
                (f"{qid}-{sequence}", qid, sequence, sub.body, sub.answer),
            )
    audit(conn, actor, "question.updated" if old else "question.created", qid)
    return qid


def management_router(cfg, session_user, public_test, active):
    router = APIRouter(prefix="/api")

    def admin(request, conn, mutation=False):
        user = session_user(request, conn, mutation)
        if not user["is_admin"]:
            raise HTTPException(403, "Len administrátor.")
        return user

    @router.post("/access-requests/{test_id}")
    def request_access(test_id: str, request: Request):
        with connect(cfg.database_url) as conn:
            user = session_user(request, conn, True)
            public_test(conn, test_id)
            conn.execute(
                "INSERT INTO test_users(user_id) VALUES(%s) ON CONFLICT DO NOTHING", (user["user_id"],)
            )
            conn.execute(
                """INSERT INTO bank_access(user_id,test_id,status) VALUES(%s,%s,'pending')
                         ON CONFLICT(user_id,test_id) DO UPDATE SET status=CASE WHEN bank_access.status='approved'
                         THEN 'approved' ELSE 'pending' END,updated_at=now()""",
                (user["user_id"], test_id),
            )
            audit(conn, user["user_id"], "access.requested", test_id)
        return {"status": "pending"}

    @router.get("/admin/users")
    def users(request: Request):
        with connect(cfg.database_url) as conn:
            admin(request, conn)
            rows = conn.execute("""SELECT u.user_id,u.approved,coalesce(jsonb_agg(jsonb_build_object('test_id',a.test_id,
                         'status',a.status)) FILTER(WHERE a.test_id IS NOT NULL),'[]') AS access
                         FROM test_users u LEFT JOIN bank_access a USING(user_id) GROUP BY u.user_id ORDER BY u.user_id""").fetchall()
            from .identity import Identity

            identity = Identity(cfg.identity_database_url)
            for row in rows:
                account = identity.find_user_by_id(user_id=row["user_id"])
                row["email"] = getattr(account, "email", None)
            return rows

    @router.put("/admin/users/{user_id}")
    def grant(user_id: str, payload: Grant, request: Request):
        with connect(cfg.database_url) as conn:
            actor = admin(request, conn, True)
            from .identity import Identity

            target = Identity(cfg.identity_database_url).find_user_by_id(user_id=user_id)
            if not target or not target.is_enabled:
                raise HTTPException(404, "Účet nie je dostupný.")
            banks = conn.execute(
                "SELECT id FROM test_definitions WHERE id=ANY(%s)", (payload.bank_ids,)
            ).fetchall()
            if len(banks) != len(set(payload.bank_ids)):
                raise HTTPException(422, "Neznáma banka.")
            conn.execute(
                """INSERT INTO test_users(user_id,approved) VALUES(%s,%s) ON CONFLICT(user_id)
                         DO UPDATE SET approved=excluded.approved,updated_at=now()""",
                (user_id, payload.approved),
            )
            conn.execute(
                "UPDATE bank_access SET status=CASE WHEN status='pending' THEN 'rejected' ELSE 'revoked' END,updated_at=now() WHERE user_id=%s",
                (user_id,),
            )
            for bank_id in payload.bank_ids:
                conn.execute(
                    """INSERT INTO bank_access(user_id,test_id,status) VALUES(%s,%s,'approved')
                             ON CONFLICT(user_id,test_id) DO UPDATE SET status='approved',updated_at=now()""",
                    (user_id, bank_id),
                )
            audit(conn, actor["user_id"], "access.updated", user_id)
        return {"status": "updated"}

    @router.get("/admin/banks")
    def banks(request: Request):
        with connect(cfg.database_url) as conn:
            admin(request, conn)
            return conn.execute("SELECT * FROM test_definitions ORDER BY name").fetchall()

    @router.put("/admin/banks/{test_id}")
    def bank(test_id: str, payload: Bank, request: Request):
        if test_id != payload.id:
            raise HTTPException(422)
        with connect(cfg.database_url) as conn:
            actor = admin(request, conn, True)
            existing = conn.execute(
                "SELECT status FROM test_definitions WHERE id=%s FOR UPDATE", (test_id,)
            ).fetchone()
            if payload.status in ("preview", "development") and (
                not existing
                or existing["status"] != payload.status
                or (payload.status == "development" and cfg.environment == "production")
            ):
                raise HTTPException(409, "Nové banky vytvorte ako návrh a potom ich publikujte po kontrole.")
            if (
                payload.status == "published"
                and not conn.execute(
                    "SELECT 1 FROM questions WHERE test_id=%s AND enabled", (test_id,)
                ).fetchone()
            ):
                raise HTTPException(409, "Pred publikovaním pridajte a skontrolujte otázky.")
            values = payload.model_dump()
            for key in ("categories", "bank_tags", "exam_categories", "source_links"):
                values[key] = Jsonb(values[key])
            conn.execute(
                """INSERT INTO test_definitions(id,name,version,description,subject,categories,bank_tags,
                exam_categories,starts_at,expires_at,status,rights_confirmed,source_links,legal_date,reviewed_by,reviewed_at,requires_legal_date)
                VALUES(%(id)s,%(name)s,%(version)s,%(description)s,%(subject)s,%(categories)s,%(bank_tags)s,
                %(exam_categories)s,%(starts_at)s,%(expires_at)s,%(status)s,%(rights_confirmed)s,%(source_links)s,%(legal_date)s,%(actor)s,now(),%(requires_legal_date)s)
                ON CONFLICT(id) DO UPDATE SET name=excluded.name,version=excluded.version,description=excluded.description,
                subject=excluded.subject,categories=excluded.categories,bank_tags=excluded.bank_tags,exam_categories=excluded.exam_categories,
                starts_at=excluded.starts_at,expires_at=excluded.expires_at,status=excluded.status,rights_confirmed=excluded.rights_confirmed,
                source_links=excluded.source_links,legal_date=excluded.legal_date,requires_legal_date=excluded.requires_legal_date,reviewed_by=excluded.reviewed_by,reviewed_at=now()""",
                {**values, "actor": actor["user_id"]},
            )
            audit(conn, actor["user_id"], "bank.updated", test_id)
        return {"status": "updated"}

    @router.get("/admin/banks/{test_id}/questions")
    def admin_questions(test_id: str, request: Request):
        with connect(cfg.database_url) as conn:
            admin(request, conn)
            rows = conn.execute(
                "SELECT * FROM questions WHERE test_id=%s ORDER BY category,number", (test_id,)
            ).fetchall()
            for row in rows:
                row["subquestions"] = conn.execute(
                    "SELECT id,body,answer FROM subquestions WHERE question_id=%s ORDER BY sequence",
                    (row["id"],),
                ).fetchall()
            return rows

    @router.post("/admin/banks/{test_id}/questions")
    @router.put("/admin/banks/{test_id}/questions/{question_id}")
    def edit_question(test_id: str, payload: QuestionInput, request: Request, question_id: str | None = None):
        try:
            with connect(cfg.database_url) as conn:
                actor = admin(request, conn, True)
                qid = save_question(conn, test_id, payload, actor["user_id"], question_id)
            return {"id": qid}
        except IntegrityError:
            raise HTTPException(409, "Skontrolujte jedinečné číslo, kategóriu a štruktúru otázky.") from None

    @router.get("/study-sets")
    def collections(request: Request):
        with connect(cfg.database_url) as conn:
            user = session_user(request, conn)
            rows = conn.execute(
                "SELECT * FROM study_sets WHERE user_id=%s ORDER BY updated_at DESC", (user["user_id"],)
            ).fetchall()
            from .access import bank_allowed

            return [r for r in rows if bank_allowed(conn, user, r["test_id"])]

    @router.post("/admin/banks/{test_id}/question-status")
    def question_status(test_id: str, payload: StatusBatch, request: Request):
        from .jobs import editable

        with connect(cfg.database_url) as conn:
            actor = admin(request, conn, True)
            if not conn.execute(
                "SELECT id FROM test_definitions WHERE id=%s FOR UPDATE", (test_id,)
            ).fetchone():
                raise HTTPException(404)
            if len({q.id for q in payload.questions}) != len(payload.questions):
                raise HTTPException(422, "Otázky nesmú byť vo výbere dvakrát.")
            for item in sorted(payload.questions, key=lambda q: q.id):
                row, question = editable(conn, item.id)
                if row["test_id"] != test_id:
                    raise HTTPException(404)
                if row["revision"] != item.revision:
                    raise HTTPException(409, "Otázky sa zmenili. Obnovte zoznam pred hromadnou zmenou.")
                if row["enabled"] == payload.enabled:
                    continue
                question.enabled = payload.enabled
                save_question(conn, test_id, question, actor["user_id"], item.id)
        return {"status": "updated"}

    @router.post("/study-sets")
    @router.put("/study-sets/{collection_id}")
    def save_collection(payload: Collection, request: Request, collection_id: UUID | None = None):
        with connect(cfg.database_url) as conn:
            user = session_user(request, conn, True)
            require_bank(conn, user, payload.test_id)
            active(public_test(conn, payload.test_id))
            if (
                collection_id
                and not conn.execute(
                    "SELECT 1 FROM study_sets WHERE id=%s AND user_id=%s", (collection_id, user["user_id"])
                ).fetchone()
            ):
                raise HTTPException(404)
            ids = list(dict.fromkeys(payload.question_ids))
            valid = conn.execute(
                "SELECT id FROM questions WHERE id=ANY(%s) AND test_id=%s AND enabled", (ids, payload.test_id)
            ).fetchall()
            if len(valid) != len(ids):
                raise HTTPException(409, "Niektoré otázky nie sú dostupné.")
            sid = collection_id or uuid4()
            conn.execute(
                """INSERT INTO study_sets(id,user_id,test_id,name,question_ids) VALUES(%s,%s,%s,%s,%s)
                ON CONFLICT(id) DO UPDATE SET name=excluded.name,question_ids=excluded.question_ids,test_id=excluded.test_id,updated_at=now()""",
                (sid, user["user_id"], payload.test_id, payload.name.strip(), Jsonb(ids)),
            )
            return {"id": str(sid)}

    @router.delete("/study-sets/{collection_id}")
    def delete_collection(collection_id: UUID, request: Request):
        with connect(cfg.database_url) as conn:
            user = session_user(request, conn, True)
            conn.execute(
                "DELETE FROM study_sets WHERE id=%s AND user_id=%s", (collection_id, user["user_id"])
            )
        return {"status": "deleted"}

    @router.post("/admin/banks/{test_id}/imports")
    def upload(
        test_id: str,
        request: Request,
        files: Annotated[list[UploadFile], File()],
        authorized: Annotated[bool, Form()] = False,
    ):
        from .jobs import store_sources

        with connect(cfg.database_url) as conn:
            actor = admin(request, conn, True)
            if not authorized:
                raise HTTPException(422, "Potvrďte oprávnenie spracovať zdrojový materiál.")
            if not conn.execute("SELECT 1 FROM test_definitions WHERE id=%s", (test_id,)).fetchone():
                raise HTTPException(404)
            jid = uuid4()
            try:
                sources, total = store_sources(jid, files)
                conn.execute(
                    """INSERT INTO bank_jobs(id,test_id,actor_id,kind,status,payload,total,model)
                     VALUES(%s,%s,%s,'import','queued',%s,%s,%s)""",
                    (jid, test_id, actor["user_id"], Jsonb(sources), total, cfg.deployment),
                )
                audit(conn, actor["user_id"], "import.queued", str(jid))
            except (ValueError, OSError):
                from .jobs import job_directory

                shutil.rmtree(job_directory(jid), ignore_errors=True)
                raise HTTPException(
                    422, "Použite platný PDF alebo zoradené PNG/JPEG; najviac 500 strán a 100 MB."
                ) from None
        return {"id": str(jid)}

    @router.post("/admin/banks/{test_id}/tagging")
    def tagging(test_id: str, payload: TagRequest, request: Request):
        with connect(cfg.database_url) as conn:
            actor = admin(request, conn, True)
            rows = conn.execute(
                "SELECT id,category,number,title,body,answer,tags,revision FROM questions WHERE test_id=%s AND id=ANY(%s)",
                (test_id, payload.question_ids),
            ).fetchall()
            if len(rows) != len(set(payload.question_ids)):
                raise HTTPException(422, "Vyberte otázky z tejto banky.")
            for row in rows:
                row["subquestions"] = conn.execute(
                    "SELECT body,answer FROM subquestions WHERE question_id=%s ORDER BY sequence",
                    (row["id"],),
                ).fetchall()
            jid = uuid4()
            conn.execute(
                """INSERT INTO bank_jobs(id,test_id,actor_id,kind,status,payload,total,model)
                  VALUES(%s,%s,%s,'tagging','queued',%s,%s,%s)""",
                (
                    jid,
                    test_id,
                    actor["user_id"],
                    Jsonb({**payload.model_dump(), "questions": rows}),
                    len(rows),
                    cfg.deployment,
                ),
            )
            audit(conn, actor["user_id"], "tagging.queued", str(jid))
        return {"id": str(jid)}

    @router.get("/admin/jobs")
    def jobs(request: Request):
        with connect(cfg.database_url) as conn:
            admin(request, conn)
            return conn.execute(
                "SELECT id,test_id,kind,status,cursor,total,error_code,provider,model,created_at FROM bank_jobs ORDER BY created_at DESC LIMIT 100"
            ).fetchall()

    @router.get("/admin/jobs/{job_id}")
    def job(job_id: UUID, request: Request):
        with connect(cfg.database_url) as conn:
            admin(request, conn)
            row = conn.execute(
                "SELECT id,test_id,kind,status,cursor,total,result,error_code,provider,model FROM bank_jobs WHERE id=%s",
                (job_id,),
            ).fetchone()
            if not row:
                raise HTTPException(404)
            return row

    @router.get("/admin/jobs/{job_id}/sources")
    def sources(job_id: UUID, request: Request):
        with connect(cfg.database_url) as conn:
            admin(request, conn)
            row = conn.execute(
                "SELECT payload FROM bank_jobs WHERE id=%s AND kind='import'", (job_id,)
            ).fetchone()
            if not row:
                raise HTTPException(404)
            return [
                {"index": index, "pages": source["pages"], "sha256": source["sha256"]}
                for index, source in enumerate(row["payload"])
            ]

    @router.get("/admin/jobs/{job_id}/sources/{source_index}")
    def source(job_id: UUID, source_index: int, request: Request):
        from .jobs import job_directory

        with connect(cfg.database_url) as conn:
            admin(request, conn)
            row = conn.execute(
                "SELECT payload FROM bank_jobs WHERE id=%s AND kind='import'", (job_id,)
            ).fetchone()
            if not row or not 0 <= source_index < len(row["payload"]):
                raise HTTPException(404)
            path = job_directory(job_id) / row["payload"][source_index]["file"]
            if not path.is_file():
                raise HTTPException(410, "Zdroj bol odstránený po uplynutí retenčnej lehoty.")
            return FileResponse(path, headers={"Content-Disposition": "inline"})

    @router.post("/admin/jobs/{job_id}/{action}")
    def job_action(job_id: UUID, action: Literal["cancel", "retry", "apply", "undo"], request: Request):
        from .jobs import apply_job, undo_tags

        try:
            with connect(cfg.database_url) as conn:
                actor = admin(request, conn, True)
                row = conn.execute("SELECT * FROM bank_jobs WHERE id=%s FOR UPDATE", (job_id,)).fetchone()
                if not row:
                    raise HTTPException(404)
                if action == "apply":
                    apply_job(conn, row, actor["user_id"])
                elif action == "undo":
                    undo_tags(conn, row, actor["user_id"])
                elif action == "retry":
                    if row["status"] not in ("error", "cancelled"):
                        raise HTTPException(409, "Úlohu teraz nemožno opakovať.")
                    conn.execute(
                        "UPDATE bank_jobs SET status='queued',error_code=NULL,lease_until=NULL,lease_token=NULL,updated_at=now() WHERE id=%s",
                        (job_id,),
                    )
                else:
                    if row["status"] == "applied":
                        raise HTTPException(409)
                    conn.execute(
                        "UPDATE bank_jobs SET status='cancelled',lease_token=NULL,updated_at=now() WHERE id=%s",
                        (job_id,),
                    )
                audit(conn, actor["user_id"], f"job.{action}", str(job_id))
            return {"status": "updated"}
        except IntegrityError:
            raise HTTPException(
                409, "Import obsahuje duplicitné čísla alebo neplatnú štruktúru. Upravte návrh."
            ) from None

    @router.put("/admin/jobs/{job_id}/review")
    def review(job_id: UUID, payload: Review, request: Request):
        with connect(cfg.database_url) as conn:
            actor = admin(request, conn, True)
            row = conn.execute("SELECT * FROM bank_jobs WHERE id=%s FOR UPDATE", (job_id,)).fetchone()
            if not row or row["kind"] != "import" or row["status"] != "review":
                raise HTTPException(409)
            conn.execute(
                "UPDATE bank_jobs SET result=%s,updated_at=now() WHERE id=%s",
                (Jsonb([r.model_dump() for r in payload.records]), job_id),
            )
            audit(conn, actor["user_id"], "import.reviewed", str(job_id))
        return {"status": "updated"}

    return router
