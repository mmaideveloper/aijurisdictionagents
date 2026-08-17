from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.document_templates.models import DocumentTemplateResponse


class CasePromptDefinition(BaseModel):
    case_prompt_id: str
    case_type_id: str
    prompt_text: str
    created_at: datetime | None = None
    updated_at: datetime | None = None


class CaseTypeDefinition(BaseModel):
    case_type_id: str
    case_type_key: str
    jurisdiction: str
    language: str | None = None
    name: str
    description: str = ""
    keywords: tuple[str, ...] = ()
    is_enabled: bool = True
    is_deleted: bool = False
    prompt: CasePromptDefinition | None = None
    templates: tuple[DocumentTemplateResponse, ...] = ()
    created_at: datetime | None = None
    updated_at: datetime | None = None
    deleted_at: datetime | None = None


class CaseTypeCreateRequest(BaseModel):
    case_type_key: str = Field(min_length=3, max_length=200)
    jurisdiction: str = Field(min_length=2, max_length=8)
    language: str | None = Field(default=None, max_length=16)
    name: str = Field(min_length=3, max_length=200)
    description: str = Field(default="", max_length=2000)
    keywords: list[str] = Field(default_factory=list)
    prompt_text: str | None = Field(default=None, min_length=20, max_length=12000)
    template_keys: list[str] = Field(default_factory=list)
    is_enabled: bool = True


class CaseTypeUpdateRequest(BaseModel):
    jurisdiction: str | None = Field(default=None, min_length=2, max_length=8)
    language: str | None = Field(default=None, max_length=16)
    name: str | None = Field(default=None, min_length=3, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    keywords: list[str] | None = None
    prompt_text: str | None = Field(default=None, min_length=20, max_length=12000)
    template_keys: list[str] | None = None
    is_enabled: bool | None = None


class CasePromptResponse(BaseModel):
    case_prompt_id: str
    prompt_text: str
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @classmethod
    def from_definition(cls, item: CasePromptDefinition) -> "CasePromptResponse":
        return cls(
            case_prompt_id=item.case_prompt_id,
            prompt_text=item.prompt_text,
            created_at=item.created_at,
            updated_at=item.updated_at,
        )


class CaseTypeResponse(BaseModel):
    case_type_id: str
    case_type_key: str
    jurisdiction: str
    language: str | None = None
    name: str
    description: str = ""
    keywords: list[str]
    is_enabled: bool
    is_deleted: bool
    prompt: CasePromptResponse | None = None
    templates: list[DocumentTemplateResponse]
    created_at: datetime | None = None
    updated_at: datetime | None = None
    deleted_at: datetime | None = None

    @classmethod
    def from_definition(cls, item: CaseTypeDefinition) -> "CaseTypeResponse":
        return cls(
            case_type_id=item.case_type_id,
            case_type_key=item.case_type_key,
            jurisdiction=item.jurisdiction,
            language=item.language,
            name=item.name,
            description=item.description,
            keywords=list(item.keywords),
            is_enabled=item.is_enabled,
            is_deleted=item.is_deleted,
            prompt=CasePromptResponse.from_definition(item.prompt) if item.prompt is not None else None,
            templates=list(item.templates),
            created_at=item.created_at,
            updated_at=item.updated_at,
            deleted_at=item.deleted_at,
        )


class CaseTypeListResponse(BaseModel):
    items: list[CaseTypeResponse]


class CaseTypeResolveResponse(BaseModel):
    matched: bool
    score: int = 0
    case_type: CaseTypeResponse | None = None

