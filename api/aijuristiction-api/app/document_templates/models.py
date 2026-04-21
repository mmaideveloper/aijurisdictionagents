from __future__ import annotations

from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field


class TemplateSourceReference(BaseModel):
    label: str = Field(min_length=3, max_length=200)
    url: str = Field(min_length=8, max_length=2000)
    publisher: str = Field(min_length=2, max_length=200)
    source_kind: str = Field(min_length=2, max_length=64)
    notes: str = Field(default="", max_length=2000)


class DocumentTemplateBasePayload(BaseModel):
    template_key: str = Field(min_length=3, max_length=200)
    jurisdiction: str = Field(min_length=2, max_length=8)
    language: str | None = Field(default=None, max_length=16)
    category: str = Field(min_length=3, max_length=200)
    title: str = Field(min_length=3, max_length=200)
    template_kind: str = Field(min_length=3, max_length=64)
    description: str = Field(default="", max_length=2000)
    source_format: str = Field(min_length=2, max_length=32)
    source_url: str = Field(min_length=8, max_length=2000)
    body: str = Field(default="", max_length=50000)
    keywords: list[str] = Field(default_factory=list)
    flow_keys: list[str] = Field(default_factory=list)
    placeholders: list[str] = Field(default_factory=list)
    source_refs: list[TemplateSourceReference] = Field(default_factory=list)
    is_enabled: bool = True


class DocumentTemplateCreateRequest(DocumentTemplateBasePayload):
    pass


class DocumentTemplateUpdateRequest(BaseModel):
    jurisdiction: str | None = Field(default=None, min_length=2, max_length=8)
    language: str | None = Field(default=None, max_length=16)
    category: str | None = Field(default=None, min_length=3, max_length=200)
    title: str | None = Field(default=None, min_length=3, max_length=200)
    template_kind: str | None = Field(default=None, min_length=3, max_length=64)
    description: str | None = Field(default=None, max_length=2000)
    source_format: str | None = Field(default=None, min_length=2, max_length=32)
    source_url: str | None = Field(default=None, min_length=8, max_length=2000)
    body: str | None = Field(default=None, max_length=50000)
    keywords: list[str] | None = None
    flow_keys: list[str] | None = None
    placeholders: list[str] | None = None
    source_refs: list[TemplateSourceReference] | None = None
    is_enabled: bool | None = None


class DocumentTemplateDefinition(BaseModel):
    template_id: str
    template_key: str
    jurisdiction: str
    language: str | None = None
    category: str
    title: str
    template_kind: str
    description: str = ""
    source_format: str
    source_url: str
    body: str = ""
    keywords: tuple[str, ...] = ()
    flow_keys: tuple[str, ...] = ()
    placeholders: tuple[str, ...] = ()
    source_refs: tuple[TemplateSourceReference, ...] = ()
    is_enabled: bool = True
    is_deleted: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None
    deleted_at: datetime | None = None


class DocumentTemplateResponse(BaseModel):
    template_id: str
    template_key: str
    jurisdiction: str
    language: str | None = None
    category: str
    title: str
    template_kind: str
    description: str = ""
    source_format: str
    source_url: str
    body: str = ""
    keywords: list[str]
    flow_keys: list[str]
    placeholders: list[str]
    source_refs: list[TemplateSourceReference]
    is_enabled: bool
    is_deleted: bool
    created_at: datetime | None = None
    updated_at: datetime | None = None
    deleted_at: datetime | None = None

    @classmethod
    def from_definition(cls, item: DocumentTemplateDefinition) -> "DocumentTemplateResponse":
        return cls(
            template_id=item.template_id,
            template_key=item.template_key,
            jurisdiction=item.jurisdiction,
            language=item.language,
            category=item.category,
            title=item.title,
            template_kind=item.template_kind,
            description=item.description,
            source_format=item.source_format,
            source_url=item.source_url,
            body=item.body,
            keywords=list(item.keywords),
            flow_keys=list(item.flow_keys),
            placeholders=list(item.placeholders),
            source_refs=list(item.source_refs),
            is_enabled=item.is_enabled,
            is_deleted=item.is_deleted,
            created_at=item.created_at,
            updated_at=item.updated_at,
            deleted_at=item.deleted_at,
        )


class DocumentTemplateListResponse(BaseModel):
    items: list[DocumentTemplateResponse]


class DocumentTemplateMatchResponse(BaseModel):
    matched: bool
    score: int = 0
    template: DocumentTemplateResponse | None = None


class RenderedTemplateResult(BaseModel):
    title: str
    lines: list[str]
    unresolved_fields: list[str]


class DownloadedTemplateSource(BaseModel):
    template_key: str
    source_url: str
    downloaded_to: Path

