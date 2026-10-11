"""Offline metadata propagation: python examples/node_execution_audit_demo.py."""
from aijurisdictionagents.correlation import correlation_scope, node_execution_scope, record_debug_event

records = []
with correlation_scope(correlation_id="synthetic-trace", debug_sink=lambda context, component, stage, status, payload: records.append(payload)):
    with node_execution_scope(run_id="synthetic-run", node_id="verify_output", occurrence_id="synthetic-attempt"):
        record_debug_event("validation", "check", "passed", {"validator_id": "synthetic-validator"})
assert records[0]["node_execution"]["occurrence_id"] == "synthetic-attempt"
print(records)
