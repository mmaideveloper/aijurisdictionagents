from __future__ import annotations

import logging
import time
from typing import Callable, List, Sequence

from ..agents import Agent
from ..documents import select_sources
from ..jurisdiction import is_slovak_language
from ..observability import TraceRecorder
from ..schemas import Document, Message, OrchestrationResult, Source

UserResponseProvider = Callable[[str, float], str | None]


class Orchestrator:
    def __init__(
        self,
        lawyer: Agent,
        judge: Agent | None,
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
        discussion_type: str = "advice",
        user_response_provider: UserResponseProvider | None = None,
    ) -> OrchestrationResult:
        if not country.strip():
            raise ValueError("country is required.")
        if question_timeout_seconds <= 0:
            raise ValueError("question_timeout_seconds must be > 0")
        if max_discussion_minutes < 0:
            raise ValueError("max_discussion_minutes must be >= 0")
        discussion_type = _normalize_discussion_type(discussion_type)
        if discussion_type not in {"advice", "court"}:
            raise ValueError("discussion_type must be 'advice' or 'court'")
        if discussion_type == "court" and self.judge is None:
            raise ValueError("judge is required for court discussion type")

        self.logger.info("Starting orchestration with %d documents", len(documents))
        output_language_hint = _output_language_hint(language)
        self.trace.record_event(
            "case_context",
            {
                "country": country,
                "output_language": language or "",
                "discussion_language": "user_input_language",
                "discussion_type": discussion_type,
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
            discussion_type=discussion_type,
            role="lawyer",
        )
        judge_prompt = None
        if self.judge is not None:
            judge_prompt = _augment_prompt(
                self.judge.system_prompt,
                country,
                output_language_hint,
                discussion_only=True,
                discussion_type=discussion_type,
                role="judge",
            )
        max_seconds = None if max_discussion_minutes == 0 else max_discussion_minutes * 60
        start_time = time.monotonic()

        last_lawyer_message: Message | None = None
        last_judge_message: Message | None = None

        while True:
            asked_user_question = False
            answered_user_question = False
            user_finished = False
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

            asked, answered, finished = self._maybe_handle_user_question(
                lawyer_message,
                conversation,
                user_response_provider,
                remaining_seconds,
                question_timeout_seconds,
                language,
            )
            if asked:
                asked_user_question = True
            if answered:
                answered_user_question = True
            if finished:
                user_finished = True

            if user_finished:
                self.logger.info("User ended discussion during agent question.")
                break
            if discussion_type == "advice":
                if self.judge is not None:
                    wants_judge = self._prompt_for_judge_review(
                        conversation,
                        user_response_provider,
                        remaining_seconds,
                        question_timeout_seconds,
                        language,
                    )
                    if wants_judge:
                        judge_message = self.judge.respond(
                            conversation,
                            [],
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

                        asked, answered, finished = self._maybe_handle_user_question(
                            judge_message,
                            conversation,
                            user_response_provider,
                            remaining_seconds,
                            question_timeout_seconds,
                            language,
                        )
                        if asked:
                            asked_user_question = True
                        if answered:
                            answered_user_question = True
                        if finished:
                            user_finished = True

                        if user_finished:
                            self.logger.info("User ended discussion during agent question.")
                            break
            else:
                if self.judge is None or judge_prompt is None:
                    raise ValueError("judge is required for court discussion type")
                judge_message = self.judge.respond(
                    conversation,
                    [],
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

                asked, answered, finished = self._maybe_handle_user_question(
                    judge_message,
                    conversation,
                    user_response_provider,
                    remaining_seconds,
                    question_timeout_seconds,
                    language,
                )
                if asked:
                    asked_user_question = True
                if answered:
                    answered_user_question = True
                if finished:
                    user_finished = True

                if user_finished:
                    self.logger.info("User ended discussion during agent question.")
                    break

                decision = _parse_judge_decision(judge_message.content)
                if decision:
                    self.trace.record_event("judge_decision", {"decision": decision})
                if decision == "rejected":
                    self.logger.info("Judge rejected lawyer response; requesting another solution.")
                    continue

            if user_finished:
                break

            remaining_seconds = _remaining_seconds(start_time, max_seconds)
            if remaining_seconds is not None and remaining_seconds <= 0:
                self.logger.info("Discussion stopped before follow-up prompt (time limit).")
                self.trace.record_event(
                    "discussion_timeout",
                    {"max_minutes": max_discussion_minutes},
                )
                break

            if asked_user_question and answered_user_question:
                continue

            should_continue = self._prompt_for_followup(
                conversation,
                user_response_provider,
                remaining_seconds,
                question_timeout_seconds,
                language,
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
            if self.judge is None:
                last_judge_message = last_lawyer_message
            else:
                last_judge_message = Message(
                    role="assistant",
                    agent_name=self.judge.name,
                    content="No judge response generated.",
                    sources=list(citations),
                )

        final_text = self._generate_final_summary(
            conversation,
            [],
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
        llm = self.judge.llm if self.judge is not None else self.lawyer.llm
        return llm.complete("FinalSummary", system_prompt, conversation, documents)

    def _maybe_handle_user_question(
        self,
        message: Message,
        conversation: List[Message],
        user_response_provider: UserResponseProvider | None,
        remaining_seconds: float | None,
        question_timeout_seconds: float,
        language: str | None,
    ) -> tuple[bool, bool, bool]:
        question = _extract_question(message.content)
        if not question:
            return False, False, False

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
            content = _no_response_message(prompt_timeout, language)
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
        if answered and _is_finish_response(content):
            self.trace.record_event("discussion_finished", {"reason": "user_finished"})
            return True, True, True
        return True, answered, False

    def _prompt_for_followup(
        self,
        conversation: List[Message],
        user_response_provider: UserResponseProvider | None,
        remaining_seconds: float | None,
        question_timeout_seconds: float,
        language: str | None,
    ) -> bool:
        if user_response_provider is None:
            return False

        prompt_timeout = question_timeout_seconds
        if remaining_seconds is not None:
            prompt_timeout = min(prompt_timeout, max(0.0, remaining_seconds))
        if prompt_timeout <= 0:
            return False

        prompt = _followup_prompt(language)
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

    def _prompt_for_judge_review(
        self,
        conversation: List[Message],
        user_response_provider: UserResponseProvider | None,
        remaining_seconds: float | None,
        question_timeout_seconds: float,
        language: str | None,
    ) -> bool:
        if user_response_provider is None:
            return False

        prompt_timeout = question_timeout_seconds
        if remaining_seconds is not None:
            prompt_timeout = min(prompt_timeout, max(0.0, remaining_seconds))
        if prompt_timeout <= 0:
            return False

        prompt = _judge_review_prompt(language)
        response = user_response_provider(prompt, prompt_timeout)
        if not response:
            self.trace.record_event(
                "user_judge_review_timeout",
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
        return _wants_judge_review(content)


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
    discussion_type: str,
    role: str,
) -> str:
    language_line = f"Respond in {output_language_hint}."
    if discussion_only and output_language_hint == "the same language as the user's instruction":
        language_line = "Respond in the same language as the user's instruction."

    court_guidance = ""
    if discussion_type == "court":
        if role == "lawyer":
            court_guidance = (
                "\nCourt mode: You represent the user's position as their legal counsel. "
                "If the recommended next step involves filing or formal court action, "
                "explicitly ask whether the user wants you to draft the proposal/pleading "
                "or prepare the court submission. Ask one clear question ending with a '?'. "
                "If key facts or documents are missing, request them directly."
            )
        elif role == "judge":
            court_guidance = (
                "\nCourt mode: Act as a validator of the lawyer's advice. Challenge weak points, "
                "surface the strongest likely opposing arguments, and request missing documents "
                "or clarifications. If the advice is incomplete or risky, explain why and what is needed. "
                "Ask specific questions ending with a '?' when information is missing."
            )

    decision_line = ""
    if discussion_type == "court" and role == "judge":
        decision_line = (
            "\nAfter your response, include a line exactly as "
            "'Decision: APPROVED' or 'Decision: REJECTED'."
        )

    return (
        f"{base_prompt}\n\n"
        f"Jurisdiction focus: Only use laws/regulations applicable to {country} "
        "or supranational rules accepted in that jurisdiction.\n"
        f"{language_line}"
        f"{court_guidance}"
        f"{decision_line}"
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


def _no_response_message(timeout_seconds: float, language: str | None) -> str:
    if timeout_seconds >= 60:
        minutes = int(round(timeout_seconds / 60))
        unit = "minute" if minutes == 1 else "minutes"
        if is_slovak_language(language):
            unit = "minúty" if minutes in {2, 3, 4} else "minút"
            return f"Používateľ nemohol odpovedať do {minutes} {unit}."
        return f"User could not answer within {minutes} {unit}."
    seconds = int(round(timeout_seconds))
    unit = "second" if seconds == 1 else "seconds"
    if is_slovak_language(language):
        unit = "sekundy" if seconds in {2, 3, 4} else "sekúnd"
        return f"Používateľ nemohol odpovedať do {seconds} {unit}."
    return f"User could not answer within {seconds} {unit}."


def _followup_prompt(language: str | None) -> str:
    if is_slovak_language(language):
        return "Máte ešte nejaké otázky? Napíšte 'finish' na ukončenie."
    return "Do you have any other questions? Type 'finish' to end."


def _judge_review_prompt(language: str | None) -> str:
    if is_slovak_language(language):
        return "Chcete, aby sudca preskúmal toto stanovisko? (áno/nie)"
    return "Do you want the judge to review this advice? (yes/no)"


def _is_finish_response(content: str) -> bool:
    cleaned = content.strip().lower()
    return cleaned in {"finish", "no", "nope", "done", "exit", "quit", "stop"}


def _wants_judge_review(content: str) -> bool:
    cleaned = content.strip().lower()
    if not cleaned:
        return False
    if cleaned in {"no", "n", "nope", "nah", "not now", "no thanks", "don't", "dont"}:
        return False
    if cleaned.startswith("no "):
        return False
    if "no judge" in cleaned or "don't judge" in cleaned or "dont judge" in cleaned:
        return False
    if "judge" in cleaned:
        return True
    return cleaned in {"yes", "y", "ok", "okay", "sure", "please"}


def _parse_judge_decision(content: str) -> str | None:
    lowered = content.lower()
    for line in lowered.splitlines():
        if "decision:" in line:
            if "approved" in line:
                return "approved"
            if "rejected" in line:
                return "rejected"
    if "decision: approved" in lowered:
        return "approved"
    if "decision: rejected" in lowered:
        return "rejected"
    return None


def _normalize_discussion_type(value: str) -> str:
    return (value or "").strip().lower()
