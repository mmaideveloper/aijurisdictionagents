"""Validate the real local API -> MCP path with an approved model and synthetic law."""

from __future__ import annotations

import base64
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import secrets
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

from dotenv import load_dotenv
import httpx


REPO_ROOT = Path(__file__).resolve().parents[1]
API_BASE_URL = "http://127.0.0.1:18080"
MCP_BASE_URL = "http://127.0.0.1:18070"
API_HEADERS = {"x-api-key": "aijuris", "Accept": "application/json"}
EXPECTED_DOCUMENT_ID = "issue-713-latest-law"
EXPECTED_IDENTIFIER = "713/2026"


def main() -> int:
    load_dotenv(REPO_ROOT / ".env", override=False)
    password = _required_env("JURISDIGTA_E2E_TEST_USER_PASSWORD")
    source_manifest = _latest_input_manifest()
    source = json.loads(source_manifest.read_text(encoding="utf-8"))
    user = source["user"]
    case_id = str(source["caseId"])
    question = str(source["question"])
    run_id = f"issue-653-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid4().hex[:8]}"
    evidence_dir = REPO_ROOT / "runs" / "e2e" / "issue-653-local-internal-mcp" / run_id
    evidence_dir.mkdir(parents=True, exist_ok=True)

    with httpx.Client(timeout=300) as client:
        access_token = _authorize_mcp(client, email=str(user["email"]), password=password)
        direct_source = _direct_mcp_source(client, access_token)

        route_response = client.get(
            f"{API_BASE_URL}/v1/model-routing/effective",
            params={"task_type": "chat_reply", "user_id": str(user["userId"])},
            headers=API_HEADERS,
        )
        route_response.raise_for_status()
        route = route_response.json()
        if route.get("route_type") == "mock" or route.get("provider") == "mock":
            raise RuntimeError("Mock model route is prohibited for issue #653 acceptance")

        session_response = client.post(
            f"{API_BASE_URL}/v1/chat/sessions",
            headers=API_HEADERS,
            json={
                "user_id": str(user["userId"]),
                "case_id": case_id,
                "country": "SK",
                "language": "sk-SK",
                "discussion_type": "advice",
            },
        )
        session_response.raise_for_status()
        session_id = str(session_response.json()["id"])

        reply_response = client.post(
            f"{API_BASE_URL}/v1/chat/sessions/{session_id}/reply",
            headers=API_HEADERS,
            json={"content": question},
        )
        reply_response.raise_for_status()
        answer = str(reply_response.json().get("content") or "")
        if EXPECTED_IDENTIFIER not in answer:
            raise AssertionError(f"Assistant answer did not contain {EXPECTED_IDENTIFIER}")

        history_response = client.get(
            f"{API_BASE_URL}/v1/cases/{case_id}/history",
            params={"user_id": str(user["userId"]), "limit": 20},
            headers=API_HEADERS,
        )
        history_response.raise_for_status()
        history = history_response.json()
        citations = history.get("citations") if isinstance(history, dict) else []
        citation = next(
            (
                item
                for item in citations or []
                if isinstance(item, dict) and str(item.get("source_id") or "") == direct_source["documentId"]
            ),
            None,
        )
        if citation is None:
            raise AssertionError("Persisted case citation did not match the direct MCP source")
        if "JurisDigta MCP" not in str(citation.get("retrieval_tool") or ""):
            raise AssertionError("Persisted citation did not identify JurisDigta MCP retrieval")

        audit_response = client.get(
            f"{API_BASE_URL}/v1/cases/{case_id}/ai-model-audit",
            params={"user_id": str(user["userId"]), "limit": 20},
            headers=API_HEADERS,
        )
        audit_response.raise_for_status()
        entries = audit_response.json().get("entries") or []
        audit = entries[0] if entries else {}

    result_manifest = {
        "schemaVersion": 1,
        "scenarioId": "issue-653-local-internal-mcp",
        "runId": run_id,
        "syntheticOnly": True,
        "services": ["api", "mcp", "postgresql-api", "postgresql-laws", "azure-foundry"],
        "realModelRoute": {
            "provider": route.get("provider"),
            "model": route.get("model"),
            "modelProfileId": route.get("model_profile_id"),
            "routeType": route.get("route_type"),
            "auditProvider": audit.get("provider"),
            "auditModel": audit.get("model"),
        },
        "expectedSourceId": EXPECTED_DOCUMENT_ID,
        "directMcpSourceId": direct_source["documentId"],
        "persistedCitationSourceId": citation.get("source_id"),
        "answerSha256": hashlib.sha256(answer.encode("utf-8")).hexdigest(),
        "backendResult": "passed",
        "frontendScreenshotResult": "pending-npm-runtime",
        "retention": "Delete ignored evidence within 7 days.",
    }
    result_path = evidence_dir / "result-manifest.json"
    result_path.write_text(json.dumps(result_manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("backend_e2e=passed")
    print(f"provider={route.get('provider')} model={route.get('model')} route_type={route.get('route_type')}")
    print(f"direct_source_id={direct_source['documentId']}")
    print(f"persisted_source_id={citation.get('source_id')}")
    print(f"manifest={result_path}")
    return 0


def _authorize_mcp(client: httpx.Client, *, email: str, password: str) -> str:
    redirect_uri = "http://127.0.0.1:47123/callback"
    registration = client.post(
        f"{MCP_BASE_URL}/oauth/register",
        json={
            "client_name": "JurisDigta issue 653 local E2E",
            "redirect_uris": [redirect_uri],
            "grant_types": ["authorization_code"],
            "response_types": ["code"],
            "token_endpoint_auth_method": "none",
            "scope": "mcp:laws",
        },
    )
    registration.raise_for_status()
    client_id = str(registration.json()["client_id"])
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).rstrip(b"=").decode()
    state = str(uuid4())
    resource = f"{MCP_BASE_URL}/MCP"
    login = client.post(
        f"{MCP_BASE_URL}/oauth/authorize/login",
        data={
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": state,
            "resource": resource,
            "scope": "mcp:laws",
            "email": email,
            "password": password,
        },
        follow_redirects=False,
    )
    if login.status_code != 303:
        raise RuntimeError(f"Synthetic MCP authorization failed with status {login.status_code}")
    callback = urlparse(login.headers["location"])
    query = parse_qs(callback.query)
    if query.get("state", [""])[0] != state:
        raise RuntimeError("Synthetic MCP authorization state mismatch")
    code = query.get("code", [""])[0]
    token = client.post(
        f"{MCP_BASE_URL}/oauth/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": client_id,
            "code_verifier": verifier,
            "resource": resource,
        },
    )
    token.raise_for_status()
    return str(token.json()["access_token"])


def _direct_mcp_source(client: httpx.Client, access_token: str) -> dict[str, str]:
    response = client.post(
        f"{MCP_BASE_URL}/MCP",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
            "MCP-Protocol-Version": "2025-11-25",
        },
        json={
            "jsonrpc": "2.0",
            "id": str(uuid4()),
            "method": "tools/call",
            "params": {
                "name": "searchLaws",
                "arguments": {
                    "query": EXPECTED_IDENTIFIER,
                    "country_code": "SK",
                    "law_number": 713,
                    "law_year": 2026,
                    "limit": 5,
                },
            },
        },
    )
    response.raise_for_status()
    envelope = response.json()
    text = next(item["text"] for item in envelope["result"]["content"] if item.get("type") == "text")
    payload = json.loads(text)
    result = next(
        (item for item in payload.get("results", []) if item.get("document_id") == EXPECTED_DOCUMENT_ID),
        None,
    )
    if result is None:
        raise AssertionError(f"Direct MCP did not return {EXPECTED_DOCUMENT_ID}")
    return {"documentId": str(result["document_id"]), "sourceUrl": str(result.get("source_url") or "")}


def _latest_input_manifest() -> Path:
    candidates = sorted((REPO_ROOT / "runs" / "e2e" / "issue-713-latest-law").glob("*/input-manifest.json"))
    if not candidates:
        raise RuntimeError("Run scripts/prepare_issue_713_latest_law_e2e.py first")
    return candidates[-1]


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if value in {"", "unknown-variable"}:
        raise RuntimeError(f"{name} must be resolved for issue #653 local acceptance")
    return value


if __name__ == "__main__":
    raise SystemExit(main())
