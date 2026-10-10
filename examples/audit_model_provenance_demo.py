"""Offline metadata example: python examples/audit_model_provenance_demo.py."""
import json

from aijurisdictionagents.api_db import AIModelRouteSelection
from aijurisdictionagents.audit_model_provenance import route_provenance

route = AIModelRouteSelection(
    policy=None, provider=None, model_profile=None, route_type="unconfigured",
    task_type="legal_analysis", plan_code="synthetic", requires_external_ack=False,
    reason="No enabled route policy matched this task and plan.",
)
print(json.dumps(route_provenance(route), indent=2))
