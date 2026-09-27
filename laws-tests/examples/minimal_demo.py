"""Run after starting the local tests API: python laws-tests/examples/minimal_demo.py."""

import sys

import httpx

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

with httpx.Client(base_url="http://127.0.0.1:8411", timeout=10) as client:
    health = client.get("/api/health")
    health.raise_for_status()
    response = client.get("/api/questions/E-1")
    response.raise_for_status()
    question = response.json()
    print(health.json()["service"])
    print(question["body"])
    print(question["answer"])
    assert client.get("/api/history").status_code == 401
    print("Public reading works; private history requires sign-in.")
    references = client.get("/api/questions/A-20").json()["subquestions"][0]["linked_body"]
    assert any(token.get("href", "").startswith("/laws/2003/555?") for token in references)
    print("Public law links present; each reader resolves the course legal date server-side.")
