"""Offline seed/citation contract: python examples/synthetic_law_anchor_demo.py."""
from pathlib import Path
import sys

root = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(root), str(root / "src"), str(root / "api/aijuristiction-api")]

from scripts.prepare_issue_635_langgraph_e2e import SYNTHETIC_PROVISION_ANCHOR  # noqa: E402
from app.mcp_law_retrieval import parse_provision_anchor  # noqa: E402

anchor = parse_provision_anchor(SYNTHETIC_PROVISION_ANCHOR)
assert anchor is not None and anchor.section_number == 569
assert parse_provision_anchor("§ 569") is None
print("Synthetic provision uses a canonical, citable section-569 anchor; no network or model call.")
