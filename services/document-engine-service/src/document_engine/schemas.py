from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class CreateDocumentRequest(BaseModel):
    document_type: str = Field(..., min_length=1, max_length=100)
    payload: dict[str, Any] = Field(default_factory=dict)
    requested_by: str | None = Field(default=None, max_length=255)
    correlation_id: str | None = Field(default=None, max_length=100)


class DocumentRequestResponse(BaseModel):
    id: str
    correlation_id: str
    status: str
    document_type: str
    requested_by: str | None
    payload: dict[str, Any]
    result: dict[str, Any] | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    finished_at: datetime | None

    model_config = {"from_attributes": True}


class HealthResponse(BaseModel):
    status: str
    service: str
    database: dict[str, str]
