from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import shutil
import uuid
from pathlib import Path
from typing import Sequence

from ..schemas import Message, OrchestrationResult


@dataclass
class CaseRecord:
    case_id: str
    path: Path
    data: dict


class CaseStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def create_case(
        self,
        *,
        instruction: str,
        country: str,
        language: str | None,
        messages: Sequence[Message],
        result: OrchestrationResult,
        agent_name: str,
        data_dir: Path | None,
        case_id: str | None = None,
    ) -> CaseRecord:
        created_at = _now()
        case_id = case_id or _generate_case_id()
        case_dir = self.root / case_id
        if case_dir.exists():
            raise ValueError(f"Case already exists: {case_id}")

        _ensure_case_dirs(case_dir)
        documents = _copy_documents(
            data_dir,
            case_dir / "documents",
            created_at,
            start_index=0,
        )
        discussion_entry = _build_discussion_entry(
            messages,
            result,
            agent_name,
            discussion_type="intake",
            created_at=created_at,
        )
        case_data = _build_case_data(
            case_id=case_id,
            instruction=instruction,
            country=country,
            language=language,
            created_at=created_at,
            documents=documents,
            discussion_entry=discussion_entry,
        )
        _write_case_json(case_dir / "case.json", case_data)
        _write_description(case_dir / "description.md", case_id, instruction, created_at)
        _write_discussion_log(
            case_dir / "discussions" / discussion_entry["log_filename"],
            discussion_entry,
            messages,
        )
        return CaseRecord(case_id=case_id, path=case_dir, data=case_data)

    def load_case(self, case_id: str) -> CaseRecord:
        case_dir = self.root / case_id
        case_path = case_dir / "case.json"
        if not case_path.exists():
            raise FileNotFoundError(f"Case not found: {case_id}")
        with case_path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        return CaseRecord(case_id=case_id, path=case_dir, data=data)

    def append_discussion(
        self,
        *,
        case_id: str,
        messages: Sequence[Message],
        result: OrchestrationResult,
        agent_name: str,
        data_dir: Path | None,
        discussion_type: str = "followup",
    ) -> CaseRecord:
        record = self.load_case(case_id)
        created_at = _now()
        documents_dir = record.path / "documents"
        documents = record.data.get("documents", [])
        new_documents = _copy_documents(
            data_dir,
            documents_dir,
            created_at,
            start_index=len(documents),
        )
        if new_documents:
            documents.extend(new_documents)
            record.data["documents"] = documents

        discussion_entry = _build_discussion_entry(
            messages,
            result,
            agent_name,
            discussion_type=discussion_type,
            created_at=created_at,
        )
        record.data.setdefault("discussions", []).append(_strip_log_filename(discussion_entry))
        record.data["open_questions"] = discussion_entry["questions_asked"]
        _write_case_json(record.path / "case.json", record.data)
        _write_discussion_log(
            record.path / "discussions" / discussion_entry["log_filename"],
            discussion_entry,
            messages,
        )
        return record


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _isoformat(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _generate_case_id() -> str:
    return f"CASE-{uuid.uuid4()}"


def _ensure_case_dirs(case_dir: Path) -> None:
    (case_dir / "documents").mkdir(parents=True, exist_ok=True)
    (case_dir / "discussions").mkdir(parents=True, exist_ok=True)
    (case_dir / "outputs").mkdir(parents=True, exist_ok=True)


def _build_case_data(
    *,
    case_id: str,
    instruction: str,
    country: str,
    language: str | None,
    created_at: datetime,
    documents: list[dict],
    discussion_entry: dict,
) -> dict:
    language_value = language or "user_input_language"
    return {
        "case_id": case_id,
        "created_at": _isoformat(created_at),
        "status": "intake_open",
        "jurisdiction": {
            "country": country,
            "language": language_value,
        },
        "parties": {
            "client": {
                "type": "",
                "name": "",
                "contact": {"email": "", "phone": ""},
            },
            "opponent": {
                "type": "",
                "name": "",
                "ico": "",
                "address": "",
            },
        },
        "matter": {
            "category": "",
            "topic": "",
            "amount_eur": None,
            "currency": "EUR",
            "key_dates": {},
            "facts_summary": instruction,
            "client_goal": "",
        },
        "documents": documents,
        "open_questions": discussion_entry["questions_asked"],
        "next_discussion": {"scheduled_for": "", "agenda": []},
        "discussions": [_strip_log_filename(discussion_entry)],
    }


def _copy_documents(
    data_dir: Path | None,
    destination: Path,
    received_at: datetime,
    start_index: int,
) -> list[dict]:
    if data_dir is None or not data_dir.exists():
        return []

    documents: list[dict] = []
    date_prefix = received_at.strftime("%Y-%m-%d")
    files = sorted(path for path in data_dir.iterdir() if path.is_file())
    for idx, path in enumerate(files, start=start_index + 1):
        filename = path.name.replace(" ", "_")
        target_name = f"{date_prefix}_{filename}"
        target_path = _dedupe_path(destination / target_name)
        shutil.copy2(path, target_path)
        documents.append(
            {
                "doc_id": f"DOC-{idx:03d}",
                "type": _infer_doc_type(path),
                "filename": target_path.name,
                "path": str(Path("documents") / target_path.name),
                "source": "user_upload",
                "received_at": _isoformat(received_at),
                "notes": "",
            }
        )
    return documents


def _dedupe_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    counter = 1
    while True:
        candidate = path.with_name(f"{stem}_{counter}{suffix}")
        if not candidate.exists():
            return candidate
        counter += 1


def _infer_doc_type(path: Path) -> str:
    extension = path.suffix.lower()
    if extension in {".txt", ".md"}:
        return "text"
    if extension == ".pdf":
        return "pdf"
    if extension in {".eml", ".msg"}:
        return "email"
    if extension in {".png", ".jpg", ".jpeg"}:
        return "image"
    if extension in {".doc", ".docx"}:
        return "document"
    return "file"


def _build_discussion_entry(
    messages: Sequence[Message],
    result: OrchestrationResult,
    agent_name: str,
    discussion_type: str,
    created_at: datetime,
) -> dict:
    agent_message = _last_agent_message(messages, agent_name)
    questions = _extract_questions(agent_message.content if agent_message else "")
    user_answers = _collect_user_answers(messages)
    summary = _summarize_message(agent_message.content if agent_message else "")
    discussion_id = f"DISC-{created_at.strftime('%Y-%m-%d-%H%M%S')}"
    log_filename = f"{created_at.strftime('%Y-%m-%dT%H-%M-%SZ')}_{discussion_type}.md"
    entry = {
        "discussion_id": discussion_id,
        "date": created_at.date().isoformat(),
        "type": discussion_type,
        "summary": summary or result.final_recommendation or "Discussion captured.",
        "questions_asked": questions,
        "client_answers": user_answers,
        "result": {
            "decisions": [result.final_recommendation] if result.final_recommendation else [],
            "risks": [result.judge_rationale] if result.judge_rationale else [],
            "next_steps": [],
        },
        "log_filename": log_filename,
    }
    return entry


def _strip_log_filename(discussion_entry: dict) -> dict:
    entry = dict(discussion_entry)
    entry.pop("log_filename", None)
    return entry


def _last_agent_message(messages: Sequence[Message], agent_name: str) -> Message | None:
    for message in reversed(messages):
        if message.role == "assistant" and message.agent_name == agent_name:
            return message
    return None


def _collect_user_answers(messages: Sequence[Message]) -> list[str]:
    if not messages:
        return []
    user_messages = [msg.content for msg in messages if msg.role == "user"]
    if len(user_messages) <= 1:
        return []
    return [content for content in user_messages[1:] if content]


def _extract_questions(text: str) -> list[str]:
    if not text:
        return []
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return [line for line in lines if "?" in line]


def _summarize_message(text: str) -> str:
    if not text:
        return ""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped[:240]
    return ""


def _write_case_json(path: Path, data: dict) -> None:
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, sort_keys=False, ensure_ascii=True)


def _write_description(path: Path, case_id: str, instruction: str, created_at: datetime) -> None:
    content = (
        f"# Case {case_id}\n\n"
        f"Created: {_isoformat(created_at)}\n\n"
        "## Instruction\n"
        f"{instruction}\n"
    )
    path.write_text(content, encoding="utf-8")


def _write_discussion_log(path: Path, discussion_entry: dict, messages: Sequence[Message]) -> None:
    lines: list[str] = []
    lines.append(f"# Discussion {discussion_entry['discussion_id']}")
    lines.append("")
    lines.append(f"Date: {discussion_entry['date']}")
    lines.append(f"Type: {discussion_entry['type']}")
    lines.append("")
    lines.append("## Summary")
    lines.append(discussion_entry["summary"])
    lines.append("")
    if discussion_entry["questions_asked"]:
        lines.append("## Questions Asked")
        for question in discussion_entry["questions_asked"]:
            lines.append(f"- {question}")
        lines.append("")
    if discussion_entry["client_answers"]:
        lines.append("## Client Answers")
        for answer in discussion_entry["client_answers"]:
            lines.append(f"- {answer}")
        lines.append("")
    lines.append("## Transcript")
    for message in messages:
        role = message.agent_name if message.role == "assistant" else "User"
        lines.append(f"{role}: {message.content}")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
