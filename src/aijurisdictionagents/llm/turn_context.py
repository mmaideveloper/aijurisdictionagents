"""Deterministic model-boundary assembly with content-free audit metadata."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Literal, Sequence

from ..schemas import Document, Message
from .turn_contracts import (
    AgentTurnContext, Artifact, ArtifactEvidence, BudgetReport, ContextBudget,
    Governance, Instruction, Provenance, Truncation, TurnMessage, TurnRequest,
)

logger = logging.getLogger(__name__)


class ContextBudgetExceeded(ValueError):
    """Required policy/request cannot fit. Never expose the offending content."""

    def __init__(self) -> None:
        super().__init__("context_budget_exceeded")


@dataclass(frozen=True)
class PreparedTurn:
    messages: tuple[dict[str, str], ...]
    report: BudgetReport


def legacy_turn_context(
    system_prompt: str, conversation: Sequence[Message], documents: Sequence[Document],
    *, budget: ContextBudget | None = None,
) -> AgentTurnContext:
    """Snapshot the legacy interface; upstream API retains authorization duties.

    No case ownership, persisted consent, or retention period is guessed from a
    filename. Legacy documents are confidential, internal and turn-scoped.
    """
    latest = len(conversation) - 1
    request = None
    if conversation and conversation[-1].role == "user":
        request = TurnRequest(text=conversation[-1].content,
                              speaker=conversation[-1].agent_name[:128])
    messages = tuple(
        TurnMessage(role=row.role[:32], speaker=row.agent_name[:128], text=row.content)
        for index, row in enumerate(conversation)
        if request is None or index != latest
    )
    artifacts = tuple(
        ArtifactEvidence(
            artifact=Artifact(
                artifact_id=doc.doc_id[:256] or f"document-{index}", kind="document",
                provenance=Provenance(source_id=doc.doc_id[:256] or f"document-{index}",
                                      source_kind="document"),
            ), filename=doc.path[:256], text=doc.content,
        ) for index, doc in enumerate(documents)
    )
    return AgentTurnContext(
        request=request, messages=messages, artifacts=artifacts,
        instructions=(Instruction(text=system_prompt,
                                  provenance=Provenance(source_id="server-policy",
                                                        source_kind="server")),),
        governance=Governance(external_processing="upstream_authorized"),
        budget=budget or ContextBudget(),
    )


def _envelope(values: dict[str, object]) -> dict[str, str]:
    return {"role": "user", "content": json.dumps(values, ensure_ascii=True)}


def _cost(messages: Sequence[dict[str, str]]) -> tuple[int, int]:
    # Byte bound is deliberately conservative, not a provider tokenizer estimate.
    # Include role strings and fixed per-message framing in both bounds.
    characters = sum(len(row["content"]) + len(row["role"]) + 16 for row in messages)
    tokens = sum(len(row["content"].encode("utf-8")) + len(row["role"]) + 16
                 for row in messages)
    return characters, tokens


def prepare_turn(context: AgentTurnContext, evidence_policy: str) -> PreparedTurn:
    """Keep policy/request intact; budget optional categories newest-history first.

    Budget the actual encoded envelopes, including JSON escaping and framing.
    Only explicit server instructions/selected first-party skill instructions have
    policy authority. Everything else is an untrusted user-role envelope.
    """
    if context.governance.processing_restricted:
        raise PermissionError("processing_restricted")
    policy = "\n\n".join(
        [instruction.text for instruction in context.instructions]
        + [skill.instruction.text for skill in context.selected_skills]
        + [evidence_policy]
    )
    system = {"role": "system", "content": policy}
    required = [system]
    request = None
    if context.request is not None:
        request = _envelope({"type": "user_request", "original_role": "user",
                             "speaker": context.request.speaker, "text": context.request.text})
        required.append(request)
    limit = context.budget

    def fits(rows: Sequence[dict[str, str]]) -> bool:
        chars, tokens = _cost(rows)
        return (chars <= limit.max_characters
                and tokens <= limit.max_tokens - limit.reserved_output_tokens)

    # Reserve a bounded disclosure envelope; a model sees categories, never hidden
    # content or identifiers, when evidence/history was omitted.
    disclosure_reserve = _envelope({"type": "context_truncated",
                                   "omitted_categories": ["messages", "artifacts", "memory", "tools"]})
    if context.messages or context.artifacts or context.memory or context.tools:
        required.append(disclosure_reserve)
    if not fits(required):
        raise ContextBudgetExceeded()
    selected: list[dict[str, str]] = []
    truncations: list[Truncation] = []

    def select(category: Literal["messages", "artifacts", "memory", "tools"],
               index: int, text: str, cap: int,
               metadata: dict[str, object]) -> dict[str, str] | None:
        capped = min(len(text), cap)
        row = _envelope({**metadata, "text": text[:capped]})
        retained = capped
        if not fits(required + selected + [row]):
            low, high = 0, capped
            while low < high:
                middle = (low + high + 1) // 2
                candidate = _envelope({**metadata, "text": text[:middle]})
                if fits(required + selected + [candidate]):
                    low = middle
                else:
                    high = middle - 1
            retained = low
            row = _envelope({**metadata, "text": text[:retained]})
        if retained < len(text):
            truncations.append(Truncation(
                category=category, index=index, original_characters=len(text),
                retained_characters=retained,
                reason="turn_limit" if retained < capped else "item_limit",
            ))
        if not fits(required + selected + [row]) or (text and retained == 0):
            # Empty metadata can itself exceed the remaining budget.
            if retained == len(text):
                truncations.append(Truncation(category=category, index=index,
                                             original_characters=len(text),
                                             retained_characters=0, reason="turn_limit"))
            return None
        selected.append(row)
        return row

    history: list[tuple[int, dict[str, str]]] = []
    for index in reversed(range(len(context.messages))):
        message = context.messages[index]
        row = select("messages", index, message.text, limit.max_item_characters,
                     {"type": "user_request" if message.role == "user" else "conversation_data",
                      "original_role": message.role, "speaker": message.speaker})
        if row is not None:
            history.append((index, row))
    evidence: list[dict[str, str]] = []
    for index, item in enumerate(context.artifacts):
        row = select("artifacts", index, item.text, limit.max_artifact_characters,
                     {"type": "untrusted_evidence", "source_id": item.artifact.provenance.source_id,
                      "filename": item.filename})
        if row is not None:
            evidence.append(row)
    for index, memory in enumerate(context.memory):
        row = select("memory", index, memory.text, limit.max_item_characters,
                     {"type": "untrusted_memory", "source_id": memory.provenance.source_id})
        if row is not None:
            evidence.append(row)
    for index, tool in enumerate(context.tools):
        row = select("tools", index, tool.description, limit.max_item_characters,
                     {"type": "available_tool", "tool_id": tool.tool_id,
                      "input_schema": json.loads(tool.input_schema_json),
                      "required_scope": tool.required_scope,
                      "approval_required": tool.approval_required, "read_only": tool.read_only})
        if row is not None:
            evidence.append(row)
    result = [system] + evidence + [row for _, row in sorted(history)]
    if truncations:
        result.append(_envelope({"type": "context_truncated",
                                 "omitted_categories": sorted({item.category for item in truncations})}))
    if request is not None:
        result.append(request)
    chars, tokens = _cost(result)
    report = BudgetReport(characters=chars, token_upper_bound=tokens,
                          truncations=tuple(truncations))
    # The audit surface intentionally excludes source/owner IDs and all text.
    logger.info("agent_turn_context schema_version=1 characters=%s token_upper_bound=%s "
                "truncated_items=%s omitted_categories=%s", chars, tokens, len(truncations),
                sorted({item.category for item in truncations}))
    return PreparedTurn(messages=tuple(result), report=report)
