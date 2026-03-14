"""Minimal runnable demo for lawyer document review workflow.

Run:
    python examples/lawyer_document_review_minimal_demo.py
"""

from __future__ import annotations

from aijurisdictionagents.agents import create_lawyer_agent
from aijurisdictionagents.llm import MockLLMClient


if __name__ == "__main__":
    lawyer = create_lawyer_agent(MockLLMClient(), "US")
    prompt = lawyer.system_prompt

    checks = {
        "asks for older version first": "older version" in prompt.lower(),
        "asks user to upload old document": "upload" in prompt.lower(),
        "updates only if outdated/incorrect": "out of date" in prompt.lower(),
    }

    for name, ok in checks.items():
        print(f"{name}: {'OK' if ok else 'MISSING'}")

    if not all(checks.values()):
        raise SystemExit("Prompt workflow checks failed")
