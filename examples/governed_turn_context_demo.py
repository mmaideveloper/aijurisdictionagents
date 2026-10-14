"""Run: python examples/governed_turn_context_demo.py (synthetic, offline)."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from aijurisdictionagents.llm.context_boundary import EVIDENCE_POLICY
from aijurisdictionagents.llm.turn_context import legacy_turn_context, prepare_turn
from aijurisdictionagents.llm.turn_contracts import ContextBudget, StreamEvent
from aijurisdictionagents.schemas import Document, Message

context = legacy_turn_context(
    "Provide a draft requiring human review.",
    [Message("user", "synthetic", "Summarize the synthetic evidence.")],
    [Document("synthetic-law", "synthetic.txt", "Public synthetic evidence. " * 1000)],
    budget=ContextBudget(max_characters=5000, max_tokens=6000, reserved_output_tokens=1000),
)
prepared = prepare_turn(context, EVIDENCE_POLICY)
assert prepared.report.characters <= 5000
assert prepared.report.token_upper_bound <= 5000
print(prepared.report.model_dump_json())
print(StreamEvent(sequence=0, event="context_truncated", omitted_categories=("artifacts",)).model_dump_json())
