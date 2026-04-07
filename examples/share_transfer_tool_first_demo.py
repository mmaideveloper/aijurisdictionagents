"""Minimal demo for the tool-first Slovak share-transfer reply path.

Run:
    python examples/share_transfer_tool_first_demo.py
"""

from __future__ import annotations

from pathlib import Path
import sys
from uuid import uuid4

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "api" / "aijuristiction-api"))

from app.chat.api import _build_slovak_share_transfer_direct_reply
from app.chat.models import Message, MessageRole


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    session_id = uuid4()
    messages = [
        Message(
            session_id=session_id,
            role=MessageRole.USER,
            agent_name="User",
            content=(
                "Chcel by som z konatela firmy spravit splocnika s 50% spoluucastou. "
                "Firma ESolutions SK s.r.o., Spisske Bystre. Priprav mi vsetky potrebne dokumenty."
            ),
        ),
        Message(
            session_id=session_id,
            role=MessageRole.ASSISTANT,
            agent_name="LawyerSlovakia",
            content="Navrh dokumentu som do chatu nezobrazila. Chcete ho vidiet?",
        ),
        Message(
            session_id=session_id,
            role=MessageRole.USER,
            agent_name="User",
            content="Ano, zobraz ho prosim.",
        ),
    ]
    company_record = {
        "name": "ESolutions SK s.r.o.",
        "registration_number": "12345678",
        "seat": "Spisske Bystre",
        "status": "Aktívna",
    }
    reply = _build_slovak_share_transfer_direct_reply(
        messages=messages,
        company_record=company_record,
    )
    print(reply)


if __name__ == "__main__":
    main()
