"""Minimal runnable demo for the deterministic Slovak tool-capabilities reply.

Prerequisite:
    Start local API first (default http://127.0.0.1:8080).

Run:
    python examples/api_tool_capabilities_demo.py
"""

from __future__ import annotations

import json
import os
import sys
from urllib import request

BASE_URL = os.environ.get("API_BASE_URL", "http://127.0.0.1:8080").rstrip("/")
API_KEY = "aijuris"


def _json_request(method: str, path: str, payload: dict[str, object]) -> dict[str, object]:
    req = request.Request(
        url=f"{BASE_URL}{path}",
        data=json.dumps(payload).encode("utf-8"),
        method=method,
        headers={
            "Content-Type": "application/json",
            "x-api-key": API_KEY,
        },
    )
    with request.urlopen(req) as response:  # nosec B310 - local demo endpoint
        decoded = json.loads(response.read().decode("utf-8"))
    if not isinstance(decoded, dict):
        raise RuntimeError(f"Unexpected JSON payload: {decoded!r}")
    return decoded


def main() -> None:
    session = _json_request(
        "POST",
        "/v1/chat/sessions",
        {"country": "SK", "discussion_type": "advice", "language": "sk-SK"},
    )
    session_id = str(session["id"])
    reply = _json_request(
        "POST",
        f"/v1/chat/sessions/{session_id}/reply",
        {
            "content": (
                "Chcem vediet zoznam vsetkych tools ktore mozem pouzit "
                "na overenie firmy, auta, adresy a katastra."
            )
        },
    )
    content = str(reply["content"])
    sys.stdout.buffer.write(content.encode("utf-8"))
    sys.stdout.buffer.write(b"\n")


if __name__ == "__main__":
    main()
