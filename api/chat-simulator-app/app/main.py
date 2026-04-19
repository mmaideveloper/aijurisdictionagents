from __future__ import annotations

import base64
import json
from importlib.metadata import PackageNotFoundError, version as package_version
from mimetypes import guess_type
from pathlib import Path
import re
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

SIMULATOR_PACKAGE = "chat-simulator-app"


app = FastAPI(
    title="AI Juristiction Chat Simulator App",
    version="0.1.21",
    description="Standalone chat simulator application for validating core chat APIs.",
)

_STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
_TESTCASES_DIR = Path(__file__).resolve().parent.parent / "testcases"

app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")


class DeleteUserCasesRequest(BaseModel):
    api_base_url: str = Field(min_length=1)
    api_key: str = Field(min_length=1)
    user_id: str | None = None
    phone_number: str | None = None
    email: str | None = None
    password: str | None = None


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
    html = (_STATIC_DIR / "index.html").read_text(encoding="utf-8")
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
