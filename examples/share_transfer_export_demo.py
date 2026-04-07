"""Minimal runnable demo for the Slovak share-transfer PDF export path.

Run:
    python examples/share_transfer_export_demo.py
"""

from __future__ import annotations

from pathlib import Path
import sys
from uuid import uuid4

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "api" / "aijuristiction-api"))
sys.path.insert(0, str(REPO_ROOT / "src"))

from app.chat.api import _build_document_export_content  # noqa: E402
from app.chat.models import Message, MessageRole, SessionResult  # noqa: E402


def main() -> None:
    session_id = uuid4()
    messages = [
        Message(
            session_id=session_id,
            role=MessageRole.USER,
            agent_name="User",
            content=(
                "Chcem z konatela firmy spravit spolocnika s 50% podielom. "
                "Firma ESolutions SK s.r.o., Spisske Bystre."
            ),
        ),
        Message(
            session_id=session_id,
            role=MessageRole.USER,
            agent_name="User",
            content=(
                "Prevod je 100% na 50 %, cena 0 EUR, ide o manzelku a potrebujem aj "
                "instrukcie pre obchodny register."
            ),
        ),
    ]
    result = SessionResult(
        final_recommendation=(
            "Pripravim pracovny navrh dokumentacie k prevodu obchodneho podielu "
            "a kontrolny zoznam podania do obchodneho registra."
        ),
        judge_rationale="Demo session result",
        metadata={"document_ready": True},
    )

    title, lines = _build_document_export_content(
        session_id=session_id,
        messages=messages,
        result=result,
        country="SK",
        language="SK",
    )

    print(title)
    print()
    for line in lines:
        print(line)


if __name__ == "__main__":
    main()
