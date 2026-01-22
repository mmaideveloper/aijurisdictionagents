from __future__ import annotations

import logging
from typing import List, Sequence

from ..agents import Agent
from ..documents import select_sources
from ..observability import TraceRecorder
from ..schemas import Document, Message, OrchestrationResult, Source


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

    def run(self, user_instruction: str, documents: Sequence[Document]) -> OrchestrationResult:
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
        lawyer_message = self.lawyer.respond(conversation, documents, citations)
        conversation.append(lawyer_message)
        self.trace.record_message(lawyer_message)

        judge_message = self.judge.respond(conversation, documents, citations)
        conversation.append(judge_message)
        self.trace.record_message(judge_message)

        final_recommendation = _build_recommendation(lawyer_message, judge_message, citations)
        result = OrchestrationResult(
            final_recommendation=final_recommendation,
            judge_rationale=judge_message.content,
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


def _build_recommendation(
    lawyer_message: Message, judge_message: Message, citations: Sequence[Source]
) -> str:
    sources_note = "" if citations else " No supporting documents were cited."
    return (
        "Recommendation: Proceed with the user's requested position, "
        "but address the judge's clarifying question and emphasize the strongest facts."
        f"{sources_note}"
    )
