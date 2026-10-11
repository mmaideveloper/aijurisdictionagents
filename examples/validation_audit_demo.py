"""Offline synthetic validator audit: python examples/validation_audit_demo.py."""
import json

from aijurisdictionagents.correlation import correlation_scope
from aijurisdictionagents.validation_audit import validation_check

def show(context, component, stage, status, payload):
    print(json.dumps(payload, indent=2))

with correlation_scope(correlation_id="synthetic-demo", debug_sink=show):
    with validation_check(category="output_quality", validator_id="synthetic.demo", validator_version="1", artifact_id="synthetic-answer-v1") as result:
        result.update(outcome="passed", reason_code="output_present", decision="continue")
