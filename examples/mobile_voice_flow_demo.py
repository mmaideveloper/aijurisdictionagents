"""Minimal runnable demo for mobile voice flow behavior."""

from dataclasses import dataclass


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
        state.awaiting_confirmation = False
    else:
        print("No speech for 10s -> Ask localized finish confirmation (for example: 'Did you finish?').")
        print("User can say no -> continue listening, yes -> send question.")
        state.awaiting_confirmation = True
    print(f"Awaiting confirmation: {state.awaiting_confirmation}")

    state.awaiting_confirmation = True
    state.pending_intent = "submit_message"
    for answer in ("ano", "nie"):
        if answer == "ano":
            print("User answered ano -> stop listening and run submit_message")
        else:
            print("User answered nie -> stop listening and cancel pending action")
        state.awaiting_confirmation = False
        state.pending_intent = None
        print(f"Awaiting confirmation: {state.awaiting_confirmation}")


if __name__ == "__main__":
    run_demo()
