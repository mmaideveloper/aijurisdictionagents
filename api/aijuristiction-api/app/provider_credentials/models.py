from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ProviderCredentialBasePayload(BaseModel):
    provider_key: str = Field(min_length=2, max_length=64)
    display_name: str = Field(min_length=2, max_length=120)
    description: str = Field(default="", max_length=1000)
    endpoint: str = Field(default="", max_length=500)
    deployment: str = Field(default="", max_length=200)
    embeddings_model: str = Field(default="", max_length=200)
    api_version: str = Field(default="", max_length=80)
    auth_method: str = Field(default="", max_length=80)
    secret_name: str = Field(default="", max_length=160)
    has_secret: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)
    is_enabled: bool = True


class ProviderCredentialCreateRequest(ProviderCredentialBasePayload):
    pass


class ProviderCredentialUpdateRequest(BaseModel):
    display_name: str | None = Field(default=None, min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=1000)
    endpoint: str | None = Field(default=None, max_length=500)
    deployment: str | None = Field(default=None, max_length=200)
    embeddings_model: str | None = Field(default=None, max_length=200)
    api_version: str | None = Field(default=None, max_length=80)
    auth_method: str | None = Field(default=None, max_length=80)
    secret_name: str | None = Field(default=None, max_length=160)
    has_secret: bool | None = None
    metadata: dict[str, Any] | None = None
    is_enabled: bool | None = None


class ProviderCredentialResponse(BaseModel):
    credential_id: str
    provider_key: str
    display_name: str
    description: str
    endpoint: str
    deployment: str
    embeddings_model: str
    api_version: str
    auth_method: str
    secret_name: str
    has_secret: bool
    metadata: dict[str, Any]
    is_enabled: bool
    is_deleted: bool
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None


class ProviderCredentialListResponse(BaseModel):
    items: list[ProviderCredentialResponse]
