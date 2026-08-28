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
    is_enabled: bool = True


class FlowPackCreateRequest(FlowPackBasePayload):
    version: int | None = Field(default=None, ge=1)


class FlowPackCreateVersionRequest(BaseModel):
    jurisdiction: str | None = Field(default=None, min_length=2, max_length=8)
    domain: str | None = Field(default=None, min_length=2, max_length=32)
    title: str | None = Field(default=None, min_length=3, max_length=200)
    description: str | None = Field(default=None, min_length=3, max_length=2000)
    definition: dict[str, Any] | None = None
    is_enabled: bool = False


class FlowPackUpdateRequest(BaseModel):
    jurisdiction: str | None = Field(default=None, min_length=2, max_length=8)
    domain: str | None = Field(default=None, min_length=2, max_length=32)
    title: str | None = Field(default=None, min_length=3, max_length=200)
    description: str | None = Field(default=None, min_length=3, max_length=2000)
    definition: dict[str, Any] | None = None


class FlowPackResponse(BaseModel):
    flow_id: str
    flow_key: str
    version: int
    jurisdiction: str
    domain: str
    title: str
    description: str
    definition: dict[str, Any]
    is_enabled: bool
    lifecycle_state: Literal["draft", "published", "retired"]
    is_deleted: bool
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None


class FlowPackListResponse(BaseModel):
    items: list[FlowPackResponse]


class FlowPackVersionListResponse(BaseModel):
    flow_key: str
    versions: list[FlowPackResponse]
