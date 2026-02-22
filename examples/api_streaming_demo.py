from __future__ import annotations

import json
from urllib import request

API_BASE = "http://localhost:8080"
HEADERS = {
    "Content-Type": "application/json",
    "x-api-key": "aijuris",
}


def _post(path: str, payload: dict) -> dict:
    req = request.Request(
        API_BASE + path,
        data=json.dumps(payload).encode("utf-8"),
        headers=HEADERS,
        method="POST",
    )
    with request.urlopen(req, timeout=30) as response:  # noqa: S310
        return json.loads(response.read().decode("utf-8"))


def main() -> None:
    session = _post(
        "/v1/chat/sessions",
        {"country": "SK", "discussion_type": "advice", "language": "en-US"},
    )
    session_id = session["id"]
    print(f"Created session: {session_id}")

    req = request.Request(
        API_BASE + f"/v1/chat/sessions/{session_id}/stream",
        data=json.dumps(
            {
                "instruction": "I need advice about late rent payment dispute.",
                "documents": [
                    {"doc_id": "lease", "path": "lease.txt", "content": "Rent due by 5th each month."}
                ],
            }
        ).encode("utf-8"),
        headers=HEADERS,
        method="POST",
    )

    with request.urlopen(req, timeout=120) as response:  # noqa: S310
        for raw_line in response:
            line = raw_line.decode("utf-8").strip()
            if line:
                print(line)


if __name__ == "__main__":
    main()
