"""Minimal runnable demo for mobile voice flow behavior."""

from dataclasses import dataclass


@dataclass
class VoiceState:
    awaiting_confirmation: bool = False
    pending_intent: str | None = None


def run_demo() -> None:
    state = VoiceState(pending_intent="create_case")
    print("Listening...")
    print("No speech for 10s -> asking confirmation")
    state.awaiting_confirmation = True
    print(f"Awaiting confirmation: {state.awaiting_confirmation}")


if __name__ == "__main__":
    run_demo()
