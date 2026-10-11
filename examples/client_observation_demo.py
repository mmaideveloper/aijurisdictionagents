"""Offline schema example: python examples/client_observation_demo.py."""
from uuid import UUID

from app.chat.client_audit import ClientObservation

observation = ClientObservation(
    user_id=UUID("00000000-0000-4000-8000-000000000001"),
    request_id="synthetic-stream-request", phase="stream_completed", elapsed_ms=123,
)
print(observation.model_dump_json(indent=2))
print("Client reports are unverified; this example sends no network request.")
