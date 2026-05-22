"""Minimal runnable demo for mobile voice flow behavior."""

from dataclasses import dataclass
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


@dataclass
class VoiceState:
    awaiting_confirmation: bool = False
    pending_intent: str | None = None


def run_demo() -> None:
    transcript = (
        "chcem vytvorit pripad s nazovom splnomocnenie 1.0 posli"
    )
    explicit_terminator = transcript.endswith("posli")
    state = VoiceState(pending_intent="create_case")
    print("Listening...")
    if explicit_terminator:
        print("Explicit terminator detected -> create_case title=splnomocnenie 1.0")
        print("Current case exists -> archive it automatically, then create the new case")
        state.awaiting_confirmation = False
    else:
        print("No speech for 5s -> Mozem uz odpovedat na otazku? Povedzte ano alebo nie.")
        state.awaiting_confirmation = True
    print(f"Awaiting confirmation: {state.awaiting_confirmation}")

    state.awaiting_confirmation = True
    state.pending_intent = "submit_message"
    for answer in ("ano", "�no", "Ã¡no", "nie"):
        normalized_answer = answer.replace("�", "a").replace("Ã¡", "a")
        if normalized_answer == "ano":
            print(f"User answered {answer} -> stop mic during processing and run submit_message")
            state.awaiting_confirmation = False
            state.pending_intent = None
        else:
            print("User answered nie -> keep draft, reopen mic, and append the next speech")
            state.awaiting_confirmation = False
            state.pending_intent = "submit_message"
        print(f"Awaiting confirmation: {state.awaiting_confirmation}")
        print(f"Pending intent: {state.pending_intent}")


if __name__ == "__main__":
    run_demo()
