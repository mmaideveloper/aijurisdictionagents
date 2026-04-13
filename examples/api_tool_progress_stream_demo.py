"""Minimal runnable demo for live tool progress events in the chat stream API.

Prerequisite:
    Start local API first (default http://127.0.0.1:8080).

Run:
    python examples/api_tool_progress_stream_demo.py
"""

from __future__ import annotations

import json
from urllib import request

BASE_URL = "http://127.0.0.1:8080"
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
        body = response.read().decode("utf-8")
    decoded = json.loads(body)
    if not isinstance(decoded, dict):
        raise RuntimeError(f"Unexpected JSON payload: {decoded!r}")
    return decoded


def main() -> None:
    session = _json_request(
        "POST",
        "/v1/chat/sessions",
        {
            "country": "SK",
            "discussion_type": "advice",
            "language": "SK",
        },
    )
    session_id = str(session["id"])

    stream_payload = {
        "instruction": (
            "Priprav mi postup a dokumentaciu pre pridanie noveho vlastnika firmy:\n"
            "Nazov: ESolutions SK s.r.o."
        ),
        "documents": [],
        "user_simulation_mode": "ReadUser",
        "communication_minutes": 30,
        "max_discussion_minutes": 60,
    }
    req = request.Request(
        url=f"{BASE_URL}/v1/chat/sessions/{session_id}/stream",
        data=json.dumps(stream_payload).encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "x-api-key": API_KEY,
        },
    )

    print(f"Streaming session: {session_id}")
    with request.urlopen(req) as response:  # nosec B310 - local demo endpoint
        current_event = ""
        for raw_line in response:
            line = raw_line.decode("utf-8").strip()
            if not line:
                continue
            if line.startswith("event: "):
                current_event = line.removeprefix("event: ").strip()
                continue
            if not line.startswith("data: "):
                continue
            payload = json.loads(line.removeprefix("data: ").strip())
            if current_event == "processing":
                print(f"[processing] {payload.get('stage')}: {payload.get('message')}")
            elif current_event == "message":
                role = payload.get("role", "unknown")
                print(f"[message:{role}] {payload.get('content')}")
            elif current_event == "done":
                print(f"[done] {payload}")
                break


if __name__ == "__main__":
    main()
