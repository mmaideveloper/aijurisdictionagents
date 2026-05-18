from __future__ import annotations

import json
import sys
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[1] / "api" / "aijuristiction-api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.voice_intent import classify_voice_intent  # noqa: E402


def main() -> None:
    decision = classify_voice_intent(
        "chcem vytvoriť prípad s nazovom splnomocnenie 1.0, pošli",
        language_code="SK",
    )
    print(
        json.dumps(
            {
                "intent": decision.intent.value,
                "confidence": decision.confidence,
                "slots": decision.slots,
                "clarification_question": decision.clarification_question,
                "routing_strategy": decision.routing_strategy,
                "transcript_redaction_hint": decision.transcript_redaction_hint,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
