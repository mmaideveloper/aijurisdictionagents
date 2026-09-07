from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class FlowPackBasePayload(BaseModel):
    flow_key: str = Field(min_length=3, description="Stable flow identifier, e.g. sk.contract.sale_purchase")
    jurisdiction: str = Field(min_length=2, max_length=8)
    domain: str = Field(min_length=2, max_length=32)
    title: str = Field(min_length=3, max_length=200)
    description: str = Field(min_length=3, max_length=2000)
    definition: dict[str, Any] = Field(default_factory=dict)
    question_kind: str = Field(min_length=2, max_length=64)
    legal_domain: str = Field(min_length=2, max_length=128)
    requested_outcome: str = Field(min_length=2, max_length=128)
    positive_examples: list[str] = Field(min_length=1, max_length=50)
    negative_examples: list[str] = Field(default_factory=list, max_length=50)
    clarification_policy: dict[str, Any] = Field(default_factory=dict)
    is_enabled: bool = False


class FlowPackCreateRequest(FlowPackBasePayload):
    version: int | None = Field(default=None, ge=1)


class FlowPackCreateVersionRequest(BaseModel):
    jurisdiction: str | None = Field(default=None, min_length=2, max_length=8)
    domain: str | None = Field(default=None, min_length=2, max_length=32)
    title: str | None = Field(default=None, min_length=3, max_length=200)
    description: str | None = Field(default=None, min_length=3, max_length=2000)
    definition: dict[str, Any] | None = None
    question_kind: str | None = Field(default=None, min_length=2, max_length=64)
    legal_domain: str | None = Field(default=None, min_length=2, max_length=128)
    requested_outcome: str | None = Field(default=None, min_length=2, max_length=128)
    positive_examples: list[str] | None = Field(default=None, min_length=1, max_length=50)
    negative_examples: list[str] | None = Field(default=None, max_length=50)
    clarification_policy: dict[str, Any] | None = None
    is_enabled: bool = False


class FlowPackUpdateRequest(BaseModel):
    jurisdiction: str | None = Field(default=None, min_length=2, max_length=8)
    domain: str | None = Field(default=None, min_length=2, max_length=32)
    title: str | None = Field(default=None, min_length=3, max_length=200)
    description: str | None = Field(default=None, min_length=3, max_length=2000)
    definition: dict[str, Any] | None = None
    question_kind: str | None = Field(default=None, min_length=2, max_length=64)
    legal_domain: str | None = Field(default=None, min_length=2, max_length=128)
    requested_outcome: str | None = Field(default=None, min_length=2, max_length=128)
    positive_examples: list[str] | None = Field(default=None, min_length=1, max_length=50)
    negative_examples: list[str] | None = Field(default=None, max_length=50)
    clarification_policy: dict[str, Any] | None = None


class FlowPackLockRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


class FlowPackResponse(BaseModel):
    flow_id: str
    flow_key: str
    version: int
    jurisdiction: str
    domain: str
    title: str
    description: str
    definition: dict[str, Any]
    question_kind: str
    legal_domain: str
    requested_outcome: str
    positive_examples: list[str]
    negative_examples: list[str]
    clarification_policy: dict[str, Any]
    definition_hash: str | None = None
    locked_at: datetime | None = None
    locked_by: str | None = None
    locked_reason: str | None = None
    is_enabled: bool
    lifecycle_state: Literal[
        "draft", "test_ready", "testing", "test_passed",
        "production_approved", "published", "retired",
    ]
    is_deleted: bool
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None


class FlowPackListResponse(BaseModel):
    items: list[FlowPackResponse]


class FlowPackVersionListResponse(BaseModel):
    flow_key: str
    versions: list[FlowPackResponse]
