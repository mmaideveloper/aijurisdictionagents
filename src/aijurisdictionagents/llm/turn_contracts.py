"""Versioned server-owned runtime contracts. Models never confer authorization.

Public contracts deliberately have no prompt, reasoning, credential or tool-payload
fields. Internal contexts must never be returned by a chat endpoint or logged.
"""
from __future__ import annotations

from datetime import datetime
import json
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Contract(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: Literal[1] = 1


class Provenance(Contract):
    source_id: str = Field(min_length=1, max_length=256)
    source_kind: Literal["server", "conversation", "document", "memory", "mcp", "tool"]
    version: str | None = Field(default=None, max_length=128)
    retrieved_at: datetime | None = None


class Retention(Contract):
    policy: Literal["turn_only", "case_policy", "explicit_expiry"] = "turn_only"
    expires_at: datetime | None = None
    deletion_scope: Literal["turn", "case", "owner"] = "turn"

    @model_validator(mode="after")
    def validate_expiry(self) -> Retention:
        if self.policy == "explicit_expiry" and self.expires_at is None:
            raise ValueError("Explicit retention requires expires_at")
        if self.expires_at is not None and self.expires_at.tzinfo is None:
            raise ValueError("Retention expiry must include timezone")
        return self


class Artifact(Contract):
    artifact_id: str = Field(min_length=1, max_length=256)
    kind: Literal["document", "retrieved_passage", "generated_document", "tool_result"]
    provenance: Provenance
    sensitivity: Literal["public", "personal", "sensitive", "confidential"] = "confidential"
    owner_scope: Literal["public", "authorized_case", "authorized_user", "turn"] = "turn"
    owner_ref: str | None = Field(default=None, max_length=256)
    retention: Retention = Field(default_factory=Retention)
    visibility: Literal["internal", "authorized_user"] = "internal"
    requires_human_review: bool = True

    @model_validator(mode="after")
    def validate_owner(self) -> Artifact:
        if self.owner_scope in {"authorized_case", "authorized_user"} and not self.owner_ref:
            raise ValueError("Owned artifact requires owner_ref")
        if self.owner_scope == "public" and self.sensitivity != "public":
            raise ValueError("Public ownership requires public sensitivity")
        return self


class ArtifactEvidence(Contract):
    artifact: Artifact
    filename: str = Field(default="", max_length=256)
    text: str = Field(repr=False)


class Instruction(Contract):
    text: str = Field(repr=False)
    provenance: Provenance

    @model_validator(mode="after")
    def validate_authority(self) -> Instruction:
        if self.provenance.source_kind != "server":
            raise ValueError("Only server-owned instructions may carry policy")
        return self


class TurnMessage(Contract):
    role: str = Field(max_length=32)
    speaker: str = Field(default="", max_length=128)
    text: str = Field(repr=False)


class TurnRequest(Contract):
    text: str = Field(repr=False)
    speaker: str = Field(default="", max_length=128)


class SelectedSkill(Contract):
    skill_id: str = Field(min_length=1, max_length=128)
    version: str = Field(min_length=1, max_length=128)
    instruction: Instruction


class ToolDefinition(Contract):
    tool_id: str = Field(min_length=1, max_length=128)
    description: str = Field(max_length=2048)
    input_schema_json: str = Field(default='{"type":"object"}', max_length=8000)
    required_scope: str = Field(min_length=1, max_length=128)
    approval_required: bool = True
    read_only: bool = True

    @model_validator(mode="after")
    def validate_schema(self) -> ToolDefinition:
        try:
            schema = json.loads(self.input_schema_json)
        except ValueError:
            raise ValueError("Tool input schema must be a JSON object schema") from None
        if not isinstance(schema, dict) or schema.get("type") != "object":
            raise ValueError("Tool input schema must be a JSON object schema")
        return self


class MemoryEvidence(Contract):
    text: str = Field(repr=False)
    provenance: Provenance
    retention: Retention = Field(default_factory=Retention)


class Governance(Contract):
    policy_version: str = Field(default="governed-turn-v1", max_length=128)
    processing_restricted: bool = False
    consent_scopes: tuple[Annotated[str, Field(min_length=1, max_length=128)], ...] = ()
    external_processing: Literal["upstream_authorized", "blocked"] = "blocked"
    human_review_required: Literal[True] = True
    log_content: Literal[False] = False


class ContextBudget(Contract):
    max_characters: int = Field(default=128000, ge=1, le=1000000)
    max_tokens: int = Field(default=128000, ge=1, le=1000000)
    reserved_output_tokens: int = Field(default=4096, ge=0)
    max_item_characters: int = Field(default=24000, ge=1, le=1000000)
    max_artifact_characters: int = Field(default=8000, ge=1, le=1000000)

    @model_validator(mode="after")
    def validate_reserve(self) -> ContextBudget:
        if self.reserved_output_tokens >= self.max_tokens:
            raise ValueError("Output reserve must be smaller than token budget")
        return self


class AgentTurnContext(Contract):
    request: TurnRequest | None = None
    instructions: tuple[Instruction, ...] = ()
    messages: tuple[TurnMessage, ...] = ()
    selected_skills: tuple[SelectedSkill, ...] = ()
    tools: tuple[ToolDefinition, ...] = ()
    memory: tuple[MemoryEvidence, ...] = ()
    artifacts: tuple[ArtifactEvidence, ...] = ()
    governance: Governance = Field(default_factory=Governance)
    provenance: tuple[Provenance, ...] = ()
    budget: ContextBudget = Field(default_factory=ContextBudget)


class Truncation(Contract):
    category: Literal["messages", "artifacts", "memory", "tools"]
    index: int = Field(ge=0)
    original_characters: int = Field(ge=0)
    retained_characters: int = Field(ge=0)
    reason: Literal["item_limit", "turn_limit"]

    @model_validator(mode="after")
    def validate_counts(self) -> Truncation:
        if self.retained_characters > self.original_characters:
            raise ValueError("Retained characters cannot exceed original characters")
        return self


class BudgetReport(Contract):
    characters: int = Field(ge=0)
    token_upper_bound: int = Field(ge=0)
    estimator: Literal["utf8-bytes-plus-message-overhead-v1"] = "utf8-bytes-plus-message-overhead-v1"
    truncations: tuple[Truncation, ...] = ()


class Approval(Contract):
    approval_id: str = Field(min_length=1, max_length=128)
    scope: str = Field(min_length=1, max_length=128)
    status: Literal["pending", "granted", "denied", "revoked"]
    expires_at: datetime | None = None

    @model_validator(mode="after")
    def validate_expiry(self) -> Approval:
        if self.expires_at is not None and self.expires_at.tzinfo is None:
            raise ValueError("Approval expiry must include timezone")
        return self


class ToolCall(Contract):
    call_id: str = Field(min_length=1, max_length=128)
    tool_id: str = Field(min_length=1, max_length=128)
    # Arguments remain private JSON, not public stream data or audit metadata.
    arguments_json: str = Field(repr=False, max_length=24000)
    approval: Approval | None = None

    @model_validator(mode="after")
    def validate_arguments(self) -> ToolCall:
        try:
            arguments = json.loads(self.arguments_json)
        except ValueError:
            raise ValueError("Tool arguments must be a JSON object") from None
        if not isinstance(arguments, dict):
            raise ValueError("Tool arguments must be a JSON object")
        return self


class ToolResult(Contract):
    call_id: str = Field(min_length=1, max_length=128)
    status: Literal["ok", "error", "approval_required"]
    artifacts: tuple[ArtifactEvidence, ...] = ()
    error_code: Literal["unavailable", "forbidden", "invalid_request"] | None = None

    @model_validator(mode="after")
    def validate_status(self) -> ToolResult:
        if (self.status == "error") != (self.error_code is not None):
            raise ValueError("Tool error status requires an error code only")
        return self


class Citation(Contract):
    source_id: str = Field(min_length=1, max_length=256)
    artifact_id: str = Field(min_length=1, max_length=256)
    locator: str | None = Field(default=None, max_length=256)
    provenance: Provenance


class PublicArtifact(Contract):
    """Explicit allowlist, created only after the caller checks ownership/access."""
    artifact_id: str = Field(min_length=1, max_length=256)
    kind: Literal["document", "retrieved_passage", "generated_document", "tool_result"]
    provenance: Provenance
    sensitivity: Literal["public", "personal", "sensitive", "confidential"]
    owner_scope: Literal["public", "authorized_case", "authorized_user", "turn"]
    retention: Retention
    requires_human_review: bool = True


class StreamEvent(Contract):
    """Public output; hidden context and tool payloads cannot be attached."""
    sequence: int = Field(ge=0)
    event: Literal["text_delta", "artifact", "citation", "approval_required", "context_truncated", "completed", "error"]
    text: str | None = Field(default=None, max_length=24000)
    artifact: PublicArtifact | None = None
    citation: Citation | None = None
    approval: Approval | None = None
    omitted_categories: tuple[Literal["messages", "artifacts", "memory", "tools"], ...] = ()
    error_code: Literal["context_budget_exceeded", "processing_restricted", "unavailable"] | None = None

    @model_validator(mode="after")
    def validate_payload(self) -> StreamEvent:
        expected = {"text_delta": self.text, "artifact": self.artifact, "citation": self.citation,
                    "approval_required": self.approval, "error": self.error_code}
        for event, value in expected.items():
            if (self.event == event) != (value is not None):
                raise ValueError("Event payload must match event type")
        if (self.event == "context_truncated") != bool(self.omitted_categories):
            raise ValueError("Truncation event requires omitted categories only")
        return self
