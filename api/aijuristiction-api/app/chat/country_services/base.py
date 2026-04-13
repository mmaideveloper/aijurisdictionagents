from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from aijurisdictionagents.schemas import Document as CoreDocument


@dataclass
class DirectReplyPreparation:
    supplemental_documents: list[CoreDocument]
    prompt_note: str = ""
    direct_reply: str | None = None
    processing_events: list[dict[str, object]] = field(default_factory=list)


def build_processing_event(
    *,
    stage: str,
    message: str,
    tool_name: str | None = None,
    details: dict[str, object] | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "stage": stage,
        "message": message,
    }
    if tool_name:
        payload["tool_name"] = tool_name
    if details:
        payload["details"] = details
    return payload


def emit_processing_event(
    *,
    events: list[dict[str, object]],
    event: dict[str, object],
    callback: Callable[[dict[str, object]], None] | None = None,
) -> None:
    events.append(event)
    if callback is not None:
        callback(event)
