"""No credentials: python examples/response_score_demo.py."""
from aijurisdictionagents.response_score import assess_response

assessment = assess_response("synthetic-answer-v1")
assert assessment.score is None and assessment.status == "incomplete"
print(assessment.model_dump_json(indent=2))
