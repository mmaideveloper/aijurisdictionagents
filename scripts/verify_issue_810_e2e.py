"""Verify real API history and route against the synthetic #810 input manifest."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
import unicodedata

import httpx


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args()
    data = json.loads(args.manifest.read_text(encoding="utf-8"))
    assert data["syntheticOnly"] is True
    with httpx.Client(base_url="http://127.0.0.1:8190", headers={"x-api-key": "aijuris"}, timeout=30) as client:
        response = client.get("/v1/cases", params={"user_id": data["user"]["userId"]})
        response.raise_for_status()
        case = next(item for item in response.json() if item["title"].startswith(f'[{data["runId"]}]'))
        history_response = client.get(f'/v1/cases/{case["case_id"]}/history', params={"user_id": data["user"]["userId"]})
        history_response.raise_for_status()
        history = history_response.json()
        assert any(item["role"] == "user" and item["content"].strip() == data["question"] for item in history["messages"]), "Frontend question must reach API history unchanged"
        answers = [item for item in history["messages"] if item["role"] == "assistant"]
        assert answers, "Real assistant answer is still pending"
        answer = answers[-1]
        text = answer["content"]
        normalized = "".join(c for c in unicodedata.normalize("NFKD", text.lower()) if not unicodedata.combining(c))
        assert "prac" in normalized and "nakup" in normalized, "Work and shopping must both be explained"
        assert "USER-FACING" not in text and "CASE_UPDATE_JSON" not in text
        assert "osobne, alebo" not in normalized
        assert "intake" not in normalized and "kontrolny zoznam" not in normalized
        assert len(re.findall(r"^#{1,6}\s+", text, re.MULTILINE)) >= 2, "Expected Markdown topic headings"
        assert re.search(r"^\|?\s*:?-{3,}", text, re.MULTILINE), "Expected a Markdown comparison table"
        prose = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith(("#", "|")))
        assert prose.count("?") <= 1, "General explanation must not append multiple follow-ups"
        assert "syntet" in normalized or "testovac" in normalized, "Synthetic source must not appear as real law"
        citations = answer.get("citations", [])
        assert data["expectedSource"]["documentId"] in {item["source_id"] for item in citations}, "Answer citation does not match MCP seed"
        # The API carries source identifiers separately; browser acceptance must
        # verify the matching identifier is rendered as a visible citation link.
        audit_response = client.get(f'/v1/cases/{case["case_id"]}/ai-model-audit', params={"user_id": data["user"]["userId"]})
        audit_response.raise_for_status()
        routes = [item for item in audit_response.json()["entries"] if item["audit_metadata"].get("model_used")]
        assert routes, "Missing actual model-use audit"
        route = routes[0]
        assert route["model"] == data["expectedModel"] and route["provider"] == data["expectedProvider"]
        assert route["model"] != "mock" and route["total_tokens"] > 0
    result = {
        "syntheticOnly": True, "runId": data["runId"], "caseId": case["case_id"],
        "expectedSource": data["expectedSource"]["documentId"],
        "observedSources": [item["source_id"] for item in citations],
        "provider": route["provider"], "model": route["model"], "routeType": route["route_type"],
        "sessionId": route["session_id"], "totalTokens": route["total_tokens"],
        "services": ["frontend:5190", "API:8190", "MCP:8191", "PostgreSQL:55410"],
        "databases": ["issue810_api", "issue810_laws"], "apiChecksPassed": True,
        "uiAcceptance": "Requires final screenshot and browser assertions", "retentionDays": 7,
    }
    path = args.manifest.parent / "result.json"
    path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"API history/citation/real-model audit checks passed. Sanitized manifest: {path}")


if __name__ == "__main__":
    main()
