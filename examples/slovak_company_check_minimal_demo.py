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
from aijurisdictionagents.tools import answer_slovak_company_seat_question
from aijurisdictionagents.tools.obchodnyregister import ObchodnyRegisterTool
from aijurisdictionagents.tools.registry import ToolRegistry


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

    print()
    print("=== Obchodný register tool demo (offline fixture) ===")
    sample_payload = (
        '{\"items\":[{\"CorporateBodyFullName\":\"ESOLUTION s.r.o.\",'
        '\"RegistrationNumber\":\"12345678\",\"RegisteredSeat\":\"Bratislava\",'
        '\"Status\":\"Active\"}]}'
    )
    tool = ObchodnyRegisterTool(requester=lambda _url: (200, "application/json", sample_payload))
    result = tool.run(company_name_or_registration="Esolution", person_name="Matonok")
    print(result.message)
    print(result.records)

    print()
    print("=== User question -> tool recognition demo ===")
    registry = ToolRegistry(_tools={"obchodny_register_company_check": tool})
    response = answer_slovak_company_seat_question(
        "Zisti mi ci spolocnost Esolution SK s.r.o. sidli v Poprade?",
        registry=registry,
    )
    print(response)
