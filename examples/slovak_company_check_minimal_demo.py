"""Minimal runnable demo for Slovak company-check prompt behavior.

Run:
    python examples/slovak_company_check_minimal_demo.py
"""

from __future__ import annotations

from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from aijurisdictionagents.agents import create_lawyer_agent
from aijurisdictionagents.llm import MockLLMClient


if __name__ == "__main__":
    lawyer = create_lawyer_agent(MockLLMClient(), "SK")
    prompt = lawyer.system_prompt
    marker = "TOOLING (dynamic checks)"
    marker_index = prompt.find(marker)
    print("=== Slovak lawyer tooling section ===")
    if marker_index >= 0:
        print(prompt[marker_index:])
    else:
        print("Tooling section not found.")
