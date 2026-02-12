"""Minimal runnable demo for Task #7 API skeleton.

Run API first:
    uvicorn app.main:app --reload --port 8080 --app-dir api/aijuristiction-api

Then:
    python examples/minimal_demo.py
"""

from __future__ import annotations

import json
from urllib import request


def get_json(url: str) -> dict:
    with request.urlopen(url, timeout=10) as response:  # noqa: S310
        return json.loads(response.read().decode("utf-8"))


if __name__ == "__main__":
    health = get_json("http://localhost:8080/health")
    version = get_json("http://localhost:8080/version")
    print("health:", health)
    print("version:", version)
