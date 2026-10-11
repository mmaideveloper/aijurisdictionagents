"""Offline: python examples/decision_evidence_demo.py (with API installed)."""
import json
from app.decision_evidence import build_decision_evidence

graph = {"runs": [{"workflow_run_id": "synthetic-run", "occurrences": [{"event_id": "synthetic-event"}]}]}
decisions = [{"workflow_run_id": "synthetic-run", "event_id": "synthetic-event", "actor": "system", "decision": {"reason_code": "unresolved_placeholder"}}]
print(json.dumps(build_decision_evidence(decisions, graph), indent=2))
