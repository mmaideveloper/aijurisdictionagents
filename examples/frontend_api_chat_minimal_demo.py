"""Minimal runnable demo for Task #238 frontend/API chat connectivity.

Run:
    python examples/frontend_api_chat_minimal_demo.py
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any


API_BASE_URL = os.getenv(
    "AIJ_API_BASE_URL",
    "https://api-juris-dev.victoriousdesert-e45eec11.westeurope.azurecontainerapps.io",
).rstrip("/")
API_KEY = os.getenv("AIJ_API_KEY", "aijuris")


def _safe_print(message: str) -> None:
    encoding = sys.stdout.encoding or "utf-8"
    sys.stdout.buffer.write((message + "\n").encode(encoding, errors="replace"))


def _request_json(method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    body = None
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url=f"{API_BASE_URL}{path}",
        method=method,
        data=body,
        headers={
            "x-api-key": API_KEY,
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            content = response.read().decode("utf-8")
            return json.loads(content) if content else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} on {path}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(
            f"Unable to connect to API at {API_BASE_URL}. "
            "Set AIJ_API_BASE_URL to a reachable API or start the local API first."
        ) from exc


def main() -> None:
    _safe_print(f"API base URL: {API_BASE_URL}")
    session = _request_json(
        "POST",
        "/v1/chat/sessions",
        {
            "country": "SK",
            "language": "en",
            "discussion_type": "advice",
            # Use a standalone API session for local frontend simulation.
            # Passing a non-existent case_id can trigger DB FK failures on /reply.
            "case_id": None,
        },
    )
    session_id = str(session.get("id", ""))
    if not session_id:
        raise RuntimeError("Session creation failed: missing session id.")
    _safe_print(f"Session created: {session_id}")

    prompts = [
        ("chat", "Please summarize the next legal step for this contract dispute."),
        ("voice", "Voice message transcript from the user: Please highlight major legal risks."),
        (
            "video",
            "Video message transcript from the user: Give a stakeholder-ready legal briefing.",
        ),
    ]
    for mode, prompt in prompts:
        reply = _request_json(
            "POST",
            f"/v1/chat/sessions/{session_id}/reply",
            {"content": prompt},
        )
        actor = reply.get("agent_name") or "AI Assistant"
        content = str(reply.get("content", "")).strip()
        _safe_print(f"\n[{mode.upper()}] {actor}")
        _safe_print(content[:400] + ("..." if len(content) > 400 else ""))


if __name__ == "__main__":
    main()
