from __future__ import annotations

import logging
import time
from typing import Callable, List, Sequence

from ..agents import Agent
from ..documents import select_sources
from ..observability import TraceRecorder
from ..schemas import Document, Message, OrchestrationResult, Source

UserResponseProvider = Callable[[str, float], str | None]


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
        country: str,
        language: str | None = None,
        question_timeout_seconds: float = 300,
        max_discussion_minutes: float = 15,
        user_response_provider: UserResponseProvider | None = None,
    ) -> OrchestrationResult:
        if not country.strip():
            raise ValueError("country is required.")
        if question_timeout_seconds <= 0:
            raise ValueError("question_timeout_seconds must be > 0")
        if max_discussion_minutes < 0:
            raise ValueError("max_discussion_minutes must be >= 0")

        self.logger.info("Starting orchestration with %d documents", len(documents))
        output_language_hint = _output_language_hint(language)
        self.trace.record_event(
            "case_context",
            {
                "country": country,
                "output_language": language or "",
                "discussion_language": "user_input_language",
            },
        )

        conversation: List[Message] = []
        user_message = Message(
            role="user",
            agent_name="User",
            content=user_instruction,
            sources=[],
        )
        conversation.append(user_message)
        self.trace.record_message(user_message)
        self.logger.info("User instruction: %s", user_instruction)

        citations = select_sources(documents, user_instruction)
        lawyer_prompt = _augment_prompt(
            self.lawyer.system_prompt,
            country,
            output_language_hint,
            discussion_only=True,
        )
        judge_prompt = _augment_prompt(
            self.judge.system_prompt,
            country,
            output_language_hint,
            discussion_only=True,
        )
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

            lawyer_message = self.lawyer.respond(
                conversation,
                documents,
                citations,
                system_prompt_override=lawyer_prompt,
            )
            conversation.append(lawyer_message)
            self.trace.record_message(lawyer_message)
            last_lawyer_message = lawyer_message
            self.logger.info("Lawyer response: %s", lawyer_message.content)

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

            self._maybe_handle_user_question(
                lawyer_message,
                conversation,
                user_response_provider,
                remaining_seconds,
                question_timeout_seconds,
            )

            judge_message = self.judge.respond(
                conversation,
                documents,
                citations,
                system_prompt_override=judge_prompt,
            )
            conversation.append(judge_message)
            self.trace.record_message(judge_message)
            last_judge_message = judge_message
            self.logger.info("Judge response: %s", judge_message.content)

            remaining_seconds = _remaining_seconds(start_time, max_seconds)
            if remaining_seconds is not None and remaining_seconds <= 0:
                self.logger.info("Discussion stopped before user prompt (time limit).")
                self.trace.record_event(
                    "discussion_timeout",
                    {"max_minutes": max_discussion_minutes},
                )
                break

            self._maybe_handle_user_question(
                judge_message,
                conversation,
                user_response_provider,
                remaining_seconds,
                question_timeout_seconds,
            )

            remaining_seconds = _remaining_seconds(start_time, max_seconds)
            if remaining_seconds is not None and remaining_seconds <= 0:
                self.logger.info("Discussion stopped before follow-up prompt (time limit).")
                self.trace.record_event(
                    "discussion_timeout",
                    {"max_minutes": max_discussion_minutes},
                )
                break

            should_continue = self._prompt_for_followup(
                conversation,
                user_response_provider,
                remaining_seconds,
                question_timeout_seconds,
            )
            if not should_continue:
                self.logger.info("User ended discussion or no follow-up provided.")
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

        final_text = self._generate_final_summary(
            conversation,
            documents,
            country,
            output_language_hint,
        )
        final_recommendation, final_rationale = _parse_final_summary(final_text)
        if not final_recommendation:
            final_recommendation = _build_recommendation(
                last_lawyer_message,
                last_judge_message,
                citations,
            )
        if not final_rationale:
            final_rationale = last_judge_message.content

        result = OrchestrationResult(
            final_recommendation=final_recommendation,
            judge_rationale=final_rationale,
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

    def _generate_final_summary(
        self,
        conversation: Sequence[Message],
        documents: Sequence[Document],
        country: str,
        output_language_hint: str,
    ) -> str:
        system_prompt = _final_summary_prompt(country, output_language_hint)
        return self.judge.llm.complete("FinalSummary", system_prompt, conversation, documents)

    def _maybe_handle_user_question(
        self,
        message: Message,
        conversation: List[Message],
        user_response_provider: UserResponseProvider | None,
        remaining_seconds: float | None,
        question_timeout_seconds: float,
    ) -> bool:
        question = _extract_question(message.content)
        if not question:
            return False

        self.logger.info("Agent asked a question: %s", question)
        prompt_timeout = question_timeout_seconds
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
            content = _no_response_message(prompt_timeout)
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

    def _prompt_for_followup(
        self,
        conversation: List[Message],
        user_response_provider: UserResponseProvider | None,
        remaining_seconds: float | None,
        question_timeout_seconds: float,
    ) -> bool:
        if user_response_provider is None:
            return False

        prompt_timeout = question_timeout_seconds
        if remaining_seconds is not None:
            prompt_timeout = min(prompt_timeout, max(0.0, remaining_seconds))
        if prompt_timeout <= 0:
            return False

        prompt = "Do you have any other questions? Type 'finish' to end."
        response = user_response_provider(prompt, prompt_timeout)
        if not response:
            self.trace.record_event(
                "user_followup_timeout",
                {"timeout_seconds": prompt_timeout},
            )
            return False

        content = response.strip()
        user_message = Message(
            role="user",
            agent_name="User",
            content=content,
            sources=[],
        )
        conversation.append(user_message)
        self.trace.record_message(user_message)
        if _is_finish_response(content):
            self.trace.record_event("discussion_finished", {"reason": "user_finished"})
            return False
        return True


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
    marker = "user focus:"
    lowered = content.lower()
    if marker in lowered:
        content = content[: lowered.index(marker)]

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


def _augment_prompt(
    base_prompt: str,
    country: str,
    output_language_hint: str,
    discussion_only: bool,
) -> str:
    language_line = "Respond in the same language as the user's instruction."
    if not discussion_only:
        language_line = f"Respond in {output_language_hint}."

    return (
        f"{base_prompt}\n\n"
        f"Jurisdiction focus: Only use laws/regulations applicable to {country} "
        "or supranational rules accepted in that jurisdiction.\n"
        f"{language_line}"
    )


def _final_summary_prompt(country: str, output_language_hint: str) -> str:
    return (
        "You are preparing the final outcome of the discussion.\n"
        f"Jurisdiction focus: Only use laws/regulations applicable to {country} "
        "or supranational rules accepted in that jurisdiction.\n"
        f"Write the final recommendation and rationale in {output_language_hint}.\n"
        "Return exactly two labeled lines:\n"
        "Recommendation: <text>\n"
        "Rationale: <text>"
    )


def _output_language_hint(language: str | None) -> str:
    cleaned = (language or "").strip()
    if cleaned:
        return cleaned
    return "the same language as the user's instruction"


def _parse_final_summary(text: str) -> tuple[str, str]:
    recommendation = ""
    rationale = ""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.lower().startswith("recommendation:"):
            recommendation = stripped.partition(":")[2].strip()
        elif stripped.lower().startswith("rationale:"):
            rationale = stripped.partition(":")[2].strip()
    if not recommendation and text.strip():
        recommendation = text.strip()
    return recommendation, rationale


def _no_response_message(timeout_seconds: float) -> str:
    if timeout_seconds >= 60:
        minutes = int(round(timeout_seconds / 60))
        unit = "minute" if minutes == 1 else "minutes"
        return f"User could not answer within {minutes} {unit}."
    seconds = int(round(timeout_seconds))
    unit = "second" if seconds == 1 else "seconds"
    return f"User could not answer within {seconds} {unit}."


def _is_finish_response(content: str) -> bool:
    cleaned = content.strip().lower()
    return cleaned in {"finish", "no", "nope", "done", "exit", "quit", "stop"}
