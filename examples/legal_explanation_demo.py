"""Offline illustration of answer normalization; no legal advice or model calls."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api" / "aijuristiction-api"))

from app.chat.api import _enforce_single_question_turn, _user_visible_text  # noqa: E402


def main() -> None:
    answer = "### Otázka?\n\nÚplná ilustračná odpoveď.\n\n### Ďalšia otázka?\n\nĎalšie podmienky."
    raw = f'USER-FACING (Slovak):\n{answer}\nCASE_UPDATE_JSON:\n{{"case":{{"open_questions":[]}}}}'
    visible = _user_visible_text(_enforce_single_question_turn(raw))
    assert visible == answer
    print(visible)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
