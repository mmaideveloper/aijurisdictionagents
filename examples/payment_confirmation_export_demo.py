"""Minimal runnable demo for Slovak payment-confirmation document export.

Run:
    python examples/payment_confirmation_export_demo.py
"""

from __future__ import annotations

from pathlib import Path
import sys
from uuid import uuid4

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "api" / "aijuristiction-api"))
sys.path.insert(0, str(REPO_ROOT / "src"))

from app.chat.api import _build_document_export_content, _current_turn_confirms_document_generation  # noqa: E402
from app.chat.models import Message, MessageRole, SessionResult  # noqa: E402


def main() -> None:
    session_id = uuid4()
    messages = [
        Message(
            session_id=session_id,
            role=MessageRole.USER,
            agent_name="User",
            content=(
                "Chcem potvrdenie o zaplateni. Platiteľ: Ján Novák. "
                "Príjemca: Marek Matonok. Suma: 120 EUR. "
                "Dátum platby: 22.05.2026. Účel platby: úhrada nájomného."
            ),
        ),
        Message(
            session_id=session_id,
            role=MessageRole.ASSISTANT,
            agent_name="LawyerSlovakia",
            content="Chcete, aby som tento dokument teraz vygeneroval vo formáte PDF?",
        ),
    ]
    print(
        "Confirmation recognized:",
        _current_turn_confirms_document_generation("�no", messages),
    )
    print()

    result = SessionResult(
        final_recommendation="Pripravil som Potvrdenie o zaplatení.",
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
