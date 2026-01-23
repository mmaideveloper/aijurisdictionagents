from __future__ import annotations

import logging
import time
from typing import Callable, List, Sequence

from ..agents import Agent
from ..documents import select_sources
from ..observability import TraceRecorder
from ..schemas import Document, Message, OrchestrationResult, Source

UserResponseProvider = Callable[[str, float], str | None]
_NO_RESPONSE_MESSAGE = "User could not answer within 1 minute."


class Orchestrator:
    def __init__(
        self,
        lawyer: Agent,
        judge: Agent,
        trace: TraceRecorder,
        logger: logging.Logger | None = None,
    ) -> None:
        self.lawyer = lawyer
        self.judge = judge
        self.trace = trace
        self.logger = logger or logging.getLogger(__name__)

    def run(
        self,
        user_instruction: str,
        documents: Sequence[Document],
        max_discussion_minutes: float = 15,
        user_response_provider: UserResponseProvider | None = None,
    ) -> OrchestrationResult:
        if max_discussion_minutes < 0:
            raise ValueError("max_discussion_minutes must be >= 0")

        self.logger.info("Starting orchestration with %d documents", len(documents))

        conversation: List[Message] = []
        user_message = Message(
            role="user",
            agent_name="User",
            content=user_instruction,
            sources=[],
        )
        conversation.append(user_message)
        self.trace.record_message(user_message)

        citations = select_sources(documents, user_instruction)
        max_seconds = None if max_discussion_minutes == 0 else max_discussion_minutes * 60
        start_time = time.monotonic()

        last_lawyer_message: Message | None = None
        last_judge_message: Message | None = None

        while True:
            if _time_exceeded(start_time, max_seconds):
                self.logger.info("Discussion stopped due to max time limit.")
                self.trace.record_event(
                    "discussion_timeout",
                    {"max_minutes": max_discussion_minutes},
                )
                break

            lawyer_message = self.lawyer.respond(conversation, documents, citations)
            conversation.append(lawyer_message)
            self.trace.record_message(lawyer_message)
            last_lawyer_message = lawyer_message

            if _time_exceeded(start_time, max_seconds):
                self.logger.info("Discussion stopped before judge turn (time limit).")
                self.trace.record_event(
                    "discussion_timeout",
                    {"max_minutes": max_discussion_minutes},
                )
                break

            remaining_seconds = _remaining_seconds(start_time, max_seconds)
            if remaining_seconds is not None and remaining_seconds <= 0:
                self.logger.info("Discussion stopped before judge prompt (time limit).")
                self.trace.record_event(
                    "discussion_timeout",
                    {"max_minutes": max_discussion_minutes},
                )
                break

            user_answered = self._maybe_handle_user_question(
                lawyer_message,
                conversation,
                user_response_provider,
                remaining_seconds,
            )

            judge_message = self.judge.respond(conversation, documents, citations)
            conversation.append(judge_message)
            self.trace.record_message(judge_message)
            last_judge_message = judge_message

            remaining_seconds = _remaining_seconds(start_time, max_seconds)
            if remaining_seconds is not None and remaining_seconds <= 0:
                self.logger.info("Discussion stopped before user prompt (time limit).")
                self.trace.record_event(
                    "discussion_timeout",
                    {"max_minutes": max_discussion_minutes},
                )
                break

            user_answered = self._maybe_handle_user_question(
                judge_message,
                conversation,
                user_response_provider,
                remaining_seconds,
            ) or user_answered

            if not user_answered:
                self.logger.info("No user response received; ending discussion.")
                break

        if last_lawyer_message is None:
            last_lawyer_message = Message(
                role="assistant",
                agent_name=self.lawyer.name,
                content="No lawyer response generated.",
                sources=list(citations),
            )
        if last_judge_message is None:
            last_judge_message = Message(
                role="assistant",
                agent_name=self.judge.name,
                content="No judge response generated.",
                sources=list(citations),
            )

        final_recommendation = _build_recommendation(
            last_lawyer_message,
            last_judge_message,
            citations,
        )
        result = OrchestrationResult(
            final_recommendation=final_recommendation,
            judge_rationale=last_judge_message.content,
            citations=list(citations),
            messages=conversation,
        )

        self.trace.record_event(
            "result",
            {
                "final_recommendation": result.final_recommendation,
                "judge_rationale": result.judge_rationale,
                "citations": [source.__dict__ for source in result.citations],
            },
        )
        self.logger.info("Orchestration complete")
        return result

    def _maybe_handle_user_question(
        self,
        message: Message,
        conversation: List[Message],
        user_response_provider: UserResponseProvider | None,
        remaining_seconds: float | None,
    ) -> bool:
        question = _extract_question(message.content)
        if not question:
            return False

        self.logger.info("Agent asked a question: %s", question)
        prompt_timeout = 60.0
        if remaining_seconds is not None:
            prompt_timeout = min(prompt_timeout, max(0.0, remaining_seconds))
        if prompt_timeout <= 0:
            response = None
        elif user_response_provider is not None:
            response = user_response_provider(question, prompt_timeout)
        else:
            response = None

        if response:
            content = response.strip()
            answered = True
        else:
            content = _NO_RESPONSE_MESSAGE
            answered = False
            self.trace.record_event(
                "user_timeout",
                {"question": question, "timeout_seconds": prompt_timeout},
            )

        user_message = Message(
            role="user",
            agent_name="User",
            content=content,
            sources=[],
        )
        conversation.append(user_message)
        self.trace.record_message(user_message)
        return answered


def _build_recommendation(
    lawyer_message: Message, judge_message: Message, citations: Sequence[Source]
) -> str:
    sources_note = "" if citations else " No supporting documents were cited."
    return (
        "Recommendation: Proceed with the user's requested position, "
        "but address the judge's clarifying question and emphasize the strongest facts."
        f"{sources_note}"
    )


def _extract_question(content: str) -> str | None:
    if "?" not in content:
        return None

    lines = [line.strip() for line in content.splitlines() if line.strip()]
    for line in reversed(lines):
        if "?" in line:
            return line
    return None


def _time_exceeded(start_time: float, max_seconds: float | None) -> bool:
    if max_seconds is None:
        return False
    return (time.monotonic() - start_time) >= max_seconds


def _remaining_seconds(start_time: float, max_seconds: float | None) -> float | None:
    if max_seconds is None:
        return None
    remaining = max_seconds - (time.monotonic() - start_time)
    return remaining
