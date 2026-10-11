"""Offline, synthetic causal projection. Run: python examples/causal_audit_demo.py."""

import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api" / "aijuristiction-api"))

from app.causal_trace import build_causal_flow  # noqa: E402


if __name__ == "__main__":
    print(json.dumps(build_causal_flow([
        {"event_id": "synthetic-api", "request_id": "request-1", "component": "api",
         "stage": "http_request", "status": "started"},
        {"event_id": "synthetic-model", "request_id": "model-1", "parent_request_id": "request-1",
         "component": "model", "stage": "completion", "status": "completed"},
    ]), indent=2))
