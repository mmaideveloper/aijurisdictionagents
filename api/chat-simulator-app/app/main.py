from __future__ import annotations

import base64
from datetime import datetime, timezone
from email.message import EmailMessage
import json
from importlib.metadata import PackageNotFoundError, version as package_version
from mimetypes import guess_type
import os
from pathlib import Path
import re
import smtplib
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

SIMULATOR_PACKAGE = "chat-simulator-app"


app = FastAPI(
    title="AI Juristiction Chat Simulator App",
    version="0.1.26",
    description="Standalone chat simulator application for validating core chat APIs.",
)

_STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
_TESTCASES_DIR = Path(__file__).resolve().parent.parent / "testcases"
_REPO_ROOT = Path(__file__).resolve().parents[3]
_EMAIL_TEST_RUNS_DIR = _REPO_ROOT / "runs" / "chat-simulator-email-tests"

app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")


class DeleteUserCasesRequest(BaseModel):
    api_base_url: str = Field(min_length=1)
    api_key: str = Field(min_length=1)
    user_id: str | None = None
    phone_number: str | None = None
    email: str | None = None
    password: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    address: str | None = None


class EmailTestSendRequest(BaseModel):
    transport: str = Field(min_length=1)
    template: str = Field(min_length=1)
    recipient: str = Field(min_length=1)
    sender: str | None = None
    smtp_host: str | None = None
    smtp_port: int | None = None
    smtp_use_tls: bool = True
    smtp_username: str | None = None
    smtp_password: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    phone_number: str | None = None
    device_id: str | None = None
    plan_code: str | None = None
    payment_provider: str | None = None
    case_subject: str | None = None
    template_version: str | None = None
    correlation_id: str | None = None


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/version")
def version() -> dict[str, str]:
    return {
        "service": "chat-simulator-app",
        "version": app.version,
        "simulator_version": _get_simulator_version(),
    }


@app.post("/internal/delete-user-cases")
def delete_user_cases(payload: DeleteUserCasesRequest) -> dict[str, Any]:
    try:
        return _delete_remote_user_cases(payload)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Delete All Cases failed: {exc}") from exc


@app.get("/", include_in_schema=False)
@app.get("/chat-simulator", include_in_schema=False)
def simulator_page() -> HTMLResponse:
    return _render_static_page("index.html")


@app.get("/email-tests", include_in_schema=False)
def email_tests_page() -> HTMLResponse:
    return _render_static_page("email-tests.html")


@app.get("/speech-to-text", include_in_schema=False)
def speech_to_text_page() -> HTMLResponse:
    return _render_static_page("speech-to-text.html")


@app.post("/internal/email-tests/send")
def send_email_test(payload: EmailTestSendRequest) -> dict[str, Any]:
    try:
        return _send_email_test(payload)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Email test failed: {exc}") from exc


@app.get("/internal/email-tests/logs", include_in_schema=False)
def email_test_logs() -> PlainTextResponse:
    log_path = _email_test_log_path()
    if not log_path.exists():
        return PlainTextResponse("No email test log entries yet.\n")
    return PlainTextResponse(log_path.read_text(encoding="utf-8", errors="replace"))


@app.get("/internal/email-tests/emails", include_in_schema=False)
def email_test_messages() -> HTMLResponse:
    emails_dir = _email_test_emails_dir()
    files = sorted(emails_dir.glob("*.eml"), key=lambda path: path.stat().st_mtime, reverse=True) if emails_dir.exists() else []
    items = [
        f'<li><a href="/internal/email-tests/emails/{path.name}">{path.name}</a></li>'
        for path in files
        if _is_safe_email_filename(path.name)
    ]
    body = "\n".join(items) if items else "<li>No generated email previews yet.</li>"
    return HTMLResponse(
        f"""<!doctype html>
<html lang="en">
  <head><meta charset="utf-8" /><title>Email test messages</title></head>
  <body>
    <h1>Email test messages</h1>
    <ul>{body}</ul>
    <p><a href="/email-tests">Back to email tests</a></p>
  </body>
</html>""",
        headers={"Cache-Control": "no-store"},
    )


@app.get("/internal/email-tests/emails/{filename}", include_in_schema=False)
def email_test_message_file(filename: str) -> FileResponse:
    if not _is_safe_email_filename(filename):
        raise HTTPException(status_code=400, detail="Invalid email filename")
    path = (_email_test_emails_dir() / filename).resolve()
    try:
        path.relative_to(_email_test_emails_dir().resolve())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid email filename") from exc
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Email preview not found")
    return FileResponse(path, media_type="message/rfc822", filename=filename)


def _render_static_page(filename: str) -> HTMLResponse:
    html = (_STATIC_DIR / "index.html").read_text(encoding="utf-8")
    if filename != "index.html":
        html = (_STATIC_DIR / filename).read_text(encoding="utf-8")
    prepared_cases_json = json.dumps(_list_testcases(), ensure_ascii=False).replace("</script>", "<\\/script>")
    rendered = (
        html.replace("__PREPARED_CASES_JSON__", prepared_cases_json)
        .replace("__SIMULATOR_VERSION__", app.version)
    )
    return HTMLResponse(
        rendered,
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
        },
    )


def _send_email_test(payload: EmailTestSendRequest) -> dict[str, Any]:
    transport = payload.transport.strip().lower()
    if transport not in {"log", "smtp"}:
        raise HTTPException(status_code=400, detail="transport must be log or smtp")

    sender = _first_non_empty(payload.sender, os.getenv("EMAIL_SENDER"), "no-reply@jurisdigta.eu")
    recipient = payload.recipient.strip()
    if not _looks_like_email(recipient):
        raise HTTPException(status_code=400, detail="recipient must be a valid email address")

    subject, body = _build_email_test_content(payload)
    message = _build_email_message(sender=sender, recipient=recipient, subject=subject, body=body)
    written_email = _write_email_preview(message=message, template=payload.template, transport=transport)

    if transport == "smtp":
        smtp_host = _first_non_empty(payload.smtp_host, os.getenv("EMAIL_SMTP_HOST"), "mail.webhouse.sk")
        smtp_port = payload.smtp_port or int(os.getenv("EMAIL_SMTP_PORT", "587"))
        smtp_username = _first_non_empty(payload.smtp_username, os.getenv("EMAIL_SMTP_USERNAME"), sender)
        smtp_password = _first_non_empty(payload.smtp_password, os.getenv("EMAIL_SMTP_PASSWORD"), "")
        _send_message_via_smtp(
            message=message,
            host=smtp_host,
            port=smtp_port,
            use_tls=payload.smtp_use_tls,
            username=smtp_username,
            password=smtp_password,
        )
        status = "sent"
    else:
        status = "logged"

    _append_email_test_log(
        {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": status,
            "transport": transport,
            "template": payload.template.strip().lower(),
            "sender": sender,
            "recipient": recipient,
            "subject": subject,
            "email_file": written_email.name,
        }
    )
    return {
        "status": status,
        "transport": transport,
        "recipient": recipient,
        "subject": subject,
        "links": {
            "logs": "/internal/email-tests/logs",
            "emails": "/internal/email-tests/emails",
            "email": f"/internal/email-tests/emails/{written_email.name}",
        },
    }


def _build_email_test_content(payload: EmailTestSendRequest) -> tuple[str, str]:
    template = payload.template.strip().lower()
    full_name = " ".join(part for part in [payload.first_name, payload.last_name] if part).strip() or "Email Tester"
    if template == "registration":
        return (
            "Your registration code",
            (
                f"Hello {full_name},\n\n"
                "Your JurisDigta registration code is: 123456\n"
                "The code expires in 30 minutes.\n"
            ),
        )
    if template == "otp":
        device_id = (payload.device_id or "chat-simulator-email-test").strip()
        return (
            "Your login code",
            (
                f"Hello {full_name},\n\n"
                "Your one time login code for mobile authentication is: 654321\n"
                f"Device ID: {device_id}\n"
                "The code expires in 30 minutes.\n"
            ),
        )
    if template == "payment":
        plan_code = (payload.plan_code or "premium").strip()
        provider = (payload.payment_provider or "paypal").strip()
        return (
            "Payment confirmed",
            (
                f"Hello {full_name},\n\n"
                f"Payment for your '{plan_code}' subscription was confirmed via {provider}. "
                "Your plan is active.\n"
            ),
        )
    if template == "documents":
        case_subject = (payload.case_subject or "Generated legal documents").strip()
        template_version = (payload.template_version or "v1").strip()
        correlation_id = (payload.correlation_id or "SIM-EMAIL-TEST").strip()
        return (
            f"Legal document package | {case_subject}",
            (
                f"Dear {full_name},\n\n"
                "Please find your generated legal documents attached. "
                "This package is prepared for your legal review and filing workflow.\n\n"
                "JurisDigta Legal Desk\n\n"
                f"Case Subject: {case_subject}\n"
                f"Version: {template_version}\n"
                f"Correlation ID: {correlation_id}\n"
            ),
        )
    raise HTTPException(status_code=400, detail="template must be registration, otp, payment, or documents")


def _build_email_message(*, sender: str, recipient: str, subject: str, body: str) -> EmailMessage:
    message = EmailMessage()
    message["From"] = sender
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(body)
    return message


def _send_message_via_smtp(
    *,
    message: EmailMessage,
    host: str,
    port: int,
    use_tls: bool,
    username: str,
    password: str,
) -> None:
    with smtplib.SMTP(host, port, timeout=15) as smtp:
        if use_tls:
            smtp.starttls()
        if username and password:
            smtp.login(username, password)
        smtp.send_message(message)


def _write_email_preview(*, message: EmailMessage, template: str, transport: str) -> Path:
    emails_dir = _email_test_emails_dir()
    emails_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
    safe_template = re.sub(r"[^a-z0-9_-]+", "-", template.strip().lower()) or "email"
    filename = f"{timestamp}-{transport}-{safe_template}.eml"
    path = emails_dir / filename
    path.write_text(message.as_string(), encoding="utf-8")
    return path


def _append_email_test_log(entry: dict[str, str]) -> None:
    log_path = _email_test_log_path()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _email_test_log_path() -> Path:
    return _EMAIL_TEST_RUNS_DIR / "email-tests.log"


def _email_test_emails_dir() -> Path:
    return _EMAIL_TEST_RUNS_DIR / "emails"


def _is_safe_email_filename(filename: str) -> bool:
    return re.fullmatch(r"[A-Za-z0-9_.-]+\.eml", filename) is not None


def _looks_like_email(value: str) -> bool:
    return re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value.strip()) is not None


def _first_non_empty(*values: str | None) -> str:
    for value in values:
        if value is None:
            continue
        stripped = value.strip()
        if stripped:
            return stripped
    return ""


def _list_testcases() -> list[dict[str, str]]:
    if not _TESTCASES_DIR.exists():
        return []
    return [_read_testcase(path) for path in sorted(_TESTCASES_DIR.glob("*.txt"))]


def _read_testcase(path: Path) -> dict[str, str]:
    raw = path.read_text(encoding="utf-8").strip()
    parsed = _parse_testcase_content(raw, fallback_title=path.stem, testcase_path=path)
    return {
        "id": path.stem,
        "filename": path.name,
        "title": str(parsed["title"]),
        "instruction": str(parsed["instruction"]),
        "documents": parsed["documents"],
    }


def _parse_testcase_content(
    raw: str,
    *,
    fallback_title: str,
    testcase_path: Path,
) -> dict[str, Any]:
    if not raw:
        return {"title": fallback_title, "instruction": "", "documents": []}

    parsed_json = _try_parse_testcase_json(raw)
    if isinstance(parsed_json, dict):
        title = str(parsed_json.get("CaseTitle") or parsed_json.get("caseTitle") or fallback_title).strip() or fallback_title
        description = str(
            parsed_json.get("CaseDescription")
            or parsed_json.get("CaseDescripton")
            or parsed_json.get("caseDescription")
            or ""
        )
        documents = _extract_testcase_documents_from_mapping(parsed_json, testcase_path=testcase_path)
        return {
            "title": title,
            "instruction": _normalize_testcase_instruction(description),
            "documents": documents,
        }

    extracted_title = _extract_testcase_title(raw, fallback_title=fallback_title)
    extracted_description = _extract_testcase_description(raw)
    extracted_documents = _extract_testcase_documents(raw, testcase_path=testcase_path)
    if extracted_description or extracted_documents:
        return {
            "title": extracted_title,
            "instruction": _normalize_testcase_instruction(extracted_description),
            "documents": extracted_documents,
        }

    first_line, separator, remainder = raw.partition("\n")
    if first_line.lower().startswith("case:"):
        title = first_line.split(":", 1)[1].strip() or fallback_title
        instruction = remainder.strip() if separator else raw
        return {
            "title": title,
            "instruction": _normalize_testcase_instruction(instruction),
            "documents": [],
        }

    return {
        "title": fallback_title,
        "instruction": _normalize_testcase_instruction(raw),
        "documents": [],
    }


def _normalize_testcase_instruction(value: str) -> str:
    return re.sub(r"\r\n?", "\n", value).strip()


def _try_parse_testcase_json(raw: str) -> dict[str, Any] | None:
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _extract_testcase_title(raw: str, *, fallback_title: str) -> str:
    title_match = re.search(r'"CaseTitle"\s*:\s*"([^"]+)"', raw, re.IGNORECASE)
    if title_match is not None:
        return title_match.group(1).strip() or fallback_title
    return fallback_title


def _extract_testcase_description(raw: str) -> str:
    description_match = re.search(
        r'"Case(?:Description|Descripiton)"\s*:\s*"?(?P<description>[\s\S]*?)(?=,\s*"(?:Documents:?|Documents)"\s*:|\}\s*$)',
        raw,
        re.IGNORECASE,
    )
    if description_match is None:
        return ""
    value = description_match.group("description").strip()
    value = value.strip('", ')
    return value


def _extract_testcase_documents_from_mapping(
    payload: dict[str, Any],
    *,
    testcase_path: Path,
) -> list[dict[str, str]]:
    raw_documents = payload.get("Documents")
    if raw_documents is None:
        raw_documents = payload.get("Documents:")
    if raw_documents is None:
        raw_documents = payload.get("documents")
    if not isinstance(raw_documents, list):
        return []
    documents: list[dict[str, str]] = []
    for item in raw_documents:
        if not isinstance(item, dict):
            continue
        file_path = str(item.get("filePath") or item.get("path") or "").strip()
        if not file_path:
            continue
        file_name = str(item.get("fileName") or item.get("name") or "").strip()
        document = _build_testcase_document_payload(
            file_path=file_path,
            file_name=file_name,
            testcase_path=testcase_path,
        )
        if document is not None:
            documents.append(document)
    return documents


def _extract_testcase_documents(raw: str, *, testcase_path: Path) -> list[dict[str, str]]:
    documents: list[dict[str, str]] = []
    object_pattern = re.compile(r"\{(?P<object_body>[\s\S]*?)\}", re.IGNORECASE)
    for match in object_pattern.finditer(raw):
        object_body = match.group("object_body")
        file_path_match = re.search(r'"filePath"\s*:\s*"(?P<file_path>[^"]+)"', object_body, re.IGNORECASE)
        if file_path_match is None:
            continue
        file_name_match = re.search(r'"fileName"\s*:\s*"(?P<file_name>[^"]+)"', object_body, re.IGNORECASE)
        document = _build_testcase_document_payload(
            file_path=file_path_match.group("file_path"),
            file_name=file_name_match.group("file_name") if file_name_match is not None else "",
            testcase_path=testcase_path,
        )
        if document is not None:
            documents.append(document)
    return documents


def _build_testcase_document_payload(
    *,
    file_path: str,
    file_name: str,
    testcase_path: Path,
) -> dict[str, str] | None:
    resolved_path = _resolve_testcase_document_path(file_path=file_path, testcase_path=testcase_path)
    if resolved_path is None or not resolved_path.exists() or not resolved_path.is_file():
        return None
    payload = resolved_path.read_bytes()
    mime_type = guess_type(resolved_path.name)[0] or "application/octet-stream"
    return {
        "fileName": file_name.strip() or resolved_path.name,
        "sourcePath": resolved_path.name,
        "mimeType": mime_type,
        "contentBase64": base64.b64encode(payload).decode("ascii"),
    }


def _resolve_testcase_document_path(*, file_path: str, testcase_path: Path) -> Path | None:
    candidate = (testcase_path.parent / file_path).resolve()
    testcase_root = _TESTCASES_DIR.resolve()
    try:
        candidate.relative_to(testcase_root)
    except ValueError:
        return None
    return candidate


def _get_simulator_version() -> str:
    try:
        return package_version(SIMULATOR_PACKAGE)
    except PackageNotFoundError:
        return app.version


def _delete_remote_user_cases(payload: DeleteUserCasesRequest) -> dict[str, Any]:
    base_url = payload.api_base_url.rstrip("/")
    user_id = (payload.user_id or "").strip() or _resolve_remote_user_id(payload, base_url=base_url)
    if not user_id:
        raise HTTPException(status_code=400, detail="User could not be resolved for Delete All Cases.")

    cases = _remote_json_request(
        method="GET",
        url=f"{base_url}/v1/cases?user_id={quote(user_id)}",
        api_key=payload.api_key,
    )
    case_items = cases if isinstance(cases, list) else []
    deleted_case_ids: list[str] = []
    failed_deletes: list[dict[str, str]] = []

    for item in case_items:
        if not isinstance(item, dict):
            continue
        case_id = str(item.get("case_id", "")).strip()
        if not case_id:
            continue
        try:
            _remote_json_request(
                method="DELETE",
                url=f"{base_url}/v1/cases/{quote(case_id)}?user_id={quote(user_id)}",
                api_key=payload.api_key,
                expect_json=False,
            )
            deleted_case_ids.append(case_id)
        except HTTPException as exc:
            failed_deletes.append({"case_id": case_id, "detail": str(exc.detail)})

    return {
        "user_id": user_id,
        "deleted_count": len(deleted_case_ids),
        "deleted_case_ids": deleted_case_ids,
        "failed_deletes": failed_deletes,
    }


def _resolve_remote_user_id(payload: DeleteUserCasesRequest, *, base_url: str) -> str:
    phone_number = (payload.phone_number or "").strip()
    email = (payload.email or "").strip()
    password = (payload.password or "").strip()

    if phone_number and email and password:
        signup_response = _remote_json_request(
            method="POST",
            url=f"{base_url}/v1/users/sign-up",
            api_key=payload.api_key,
            body={
                "phone_number": phone_number,
                "email": email,
                "password": password,
                "first_name": (payload.first_name or "").strip() or None,
                "last_name": (payload.last_name or "").strip() or None,
                "address": (payload.address or "").strip() or None,
            },
            allow_statuses={409},
        )
        if isinstance(signup_response, dict) and signup_response.get("user_id"):
            return str(signup_response["user_id"]).strip()

    if phone_number:
        phone_signin = _remote_json_request(
            method="POST",
            url=f"{base_url}/v1/users/sign-in/phone",
            api_key=payload.api_key,
            body={"phone_number": phone_number},
            allow_statuses={404},
        )
        if isinstance(phone_signin, dict) and phone_signin.get("user_id"):
            return str(phone_signin["user_id"]).strip()

    if email and password:
        signin = _remote_json_request(
            method="POST",
            url=f"{base_url}/v1/users/sign-in",
            api_key=payload.api_key,
            body={"email": email, "password": password},
        )
        if isinstance(signin, dict) and signin.get("user_id"):
            return str(signin["user_id"]).strip()

    return ""


def _remote_json_request(
    *,
    method: str,
    url: str,
    api_key: str,
    body: dict[str, Any] | None = None,
    expect_json: bool = True,
    allow_statuses: set[int] | None = None,
) -> Any:
    payload = None if body is None else json.dumps(body).encode("utf-8")
    headers = {
        "x-api-key": api_key,
        "Accept": "application/json",
    }
    if payload is not None:
        headers["Content-Type"] = "application/json"
    request = Request(url, data=payload, headers=headers, method=method)
    try:
        with urlopen(request, timeout=30) as response:  # noqa: S310
            raw = response.read().decode("utf-8", errors="replace")
            if not expect_json:
                return raw
            return json.loads(raw) if raw.strip() else {}
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        if allow_statuses and exc.code in allow_statuses:
            return json.loads(raw) if raw.strip() else {}
        detail = raw.strip() or f"HTTP {exc.code}"
        raise HTTPException(status_code=exc.code, detail=detail) from exc
    except URLError as exc:
        raise HTTPException(status_code=502, detail=f"Remote API unreachable: {exc.reason}") from exc
