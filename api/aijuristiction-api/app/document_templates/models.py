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


class TemplateFactField(BaseModel):
    key: str = Field(min_length=2, max_length=100, pattern=r"^[a-z][a-z0-9_]*$")
    label: str = Field(min_length=2, max_length=200)
    required: bool = True
    question: str = Field(min_length=3, max_length=500)
    aliases: list[str] = Field(default_factory=list)
    profile_sources: list[str] = Field(default_factory=list)
    default_value: str = Field(default="", max_length=1000)
    description: str = Field(default="", max_length=1000)


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
    fact_schema: list[TemplateFactField] = Field(default_factory=list)
    source_refs: list[TemplateSourceReference] = Field(default_factory=list)
    disclaimer_title: str = Field(default="", max_length=200)
    disclaimer_text: str = Field(default="", max_length=4000)
    disclaimer_footer: str = Field(default="", max_length=300)
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
    fact_schema: list[TemplateFactField] | None = None
    source_refs: list[TemplateSourceReference] | None = None
    disclaimer_title: str | None = Field(default=None, max_length=200)
    disclaimer_text: str | None = Field(default=None, max_length=4000)
    disclaimer_footer: str | None = Field(default=None, max_length=300)
    is_enabled: bool | None = None


class DocumentTemplateDefinition(BaseModel):
    template_id: str
    template_key: str
    lineage_key: str = ""
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
    fact_schema: tuple[TemplateFactField, ...] = ()
    source_refs: tuple[TemplateSourceReference, ...] = ()
    disclaimer_title: str = ""
    disclaimer_text: str = ""
    disclaimer_footer: str = ""
    is_enabled: bool = True
    is_deleted: bool = False
    version: int = 1
    latest_version: int = 1
    stored_at: datetime | None = None
    newer_version_available: bool = False
    is_latest_version: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None
    deleted_at: datetime | None = None


class DocumentTemplateResponse(BaseModel):
    template_id: str
    template_key: str
    lineage_key: str = ""
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
    fact_schema: list[TemplateFactField]
    source_refs: list[TemplateSourceReference]
    disclaimer_title: str = ""
    disclaimer_text: str = ""
    disclaimer_footer: str = ""
    is_enabled: bool
    is_deleted: bool
    version: int
    latest_version: int
    stored_at: datetime | None = None
    newer_version_available: bool
    is_latest_version: bool
    created_at: datetime | None = None
    updated_at: datetime | None = None
    deleted_at: datetime | None = None

    @classmethod
    def from_definition(cls, item: DocumentTemplateDefinition) -> "DocumentTemplateResponse":
        return cls(
            template_id=item.template_id,
            template_key=item.template_key,
            lineage_key=item.lineage_key,
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
            fact_schema=list(item.fact_schema),
            source_refs=list(item.source_refs),
            disclaimer_title=item.disclaimer_title,
            disclaimer_text=item.disclaimer_text,
            disclaimer_footer=item.disclaimer_footer,
            is_enabled=item.is_enabled,
            is_deleted=item.is_deleted,
            version=item.version,
            latest_version=item.latest_version,
            stored_at=item.stored_at,
            newer_version_available=item.newer_version_available,
            is_latest_version=item.is_latest_version,
            created_at=item.created_at,
            updated_at=item.updated_at,
            deleted_at=item.deleted_at,
        )


class DocumentTemplateListResponse(BaseModel):
    items: list[DocumentTemplateResponse]


class DocumentTemplateVersionListResponse(BaseModel):
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

