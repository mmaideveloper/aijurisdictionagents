from __future__ import annotations

from dataclasses import dataclass, replace
from hashlib import sha256
import json


@dataclass(frozen=True)
class ProvisionRecord:
    anchor: str
    heading: str
    text: str


@dataclass(frozen=True)
class LawInformationField:
    label: str
    value: str


@dataclass(frozen=True)
class LawMetadataRecord:
    law_identifier_text: str
    title: str
    law_type: str
    approval_date: str | None
    publication_date: str
    effective_from: str
    effective_to: str | None
    author: str | None
    legal_areas: tuple[str, ...]
    issue_reference: str | None
    fields: tuple[LawInformationField, ...] = ()

    def normalized_payload(self) -> dict[str, object]:
        return {
            "law_identifier_text": self.law_identifier_text,
            "title": self.title,
            "law_type": self.law_type,
            "approval_date": self.approval_date,
            "publication_date": self.publication_date,
            "effective_from": self.effective_from,
            "effective_to": self.effective_to,
            "author": self.author,
            "legal_areas": list(self.legal_areas),
            "issue_reference": self.issue_reference,
            "fields": [
                {"label": field.label, "value": field.value}
                for field in self.fields
            ],
        }


@dataclass(frozen=True)
class LawRelationRecord:
    relation_type: str
    relation_label: str
    target_law_identifier_text: str
    target_title: str
    target_url: str
    target_country_code: str = "SK"
    target_collection_code: str = "ZZ"
    target_law_year: int | None = None
    target_law_number: int | None = None

    def normalized_payload(self) -> dict[str, object]:
        return {
            "relation_type": self.relation_type,
            "relation_label": self.relation_label,
            "target_law_identifier_text": self.target_law_identifier_text,
            "target_title": self.target_title,
            "target_url": self.target_url,
            "target_country_code": self.target_country_code,
            "target_collection_code": self.target_collection_code,
            "target_law_year": self.target_law_year,
            "target_law_number": self.target_law_number,
        }


@dataclass(frozen=True)
class LawSnapshot:
    source_system: str
    country_code: str
    collection_code: str
    year: int
    number: int
    official_name: str
    lawyer_title: str
    publication_date: str
    effective_from: str
    version_token: str
    source_url: str
    html_url: str
    pdf_url: str
    html_content: str
    pdf_content: bytes
    provisions: tuple[ProvisionRecord, ...]
    status: str = "published"
    applicable_to: str | None = None
    superseded_by_url: str = ""
    parent_law_year: int | None = None
    parent_law_number: int | None = None
    metadata: LawMetadataRecord | None = None
    relations: tuple[LawRelationRecord, ...] = ()
    http_etag: str = ""
    http_last_modified: str = ""

    def document_key(self) -> str:
        return f"{self.country_code}-{self.collection_code}-{self.year}-{self.number}"

    def normalized_payload(self) -> dict[str, object]:
        return {
            "country_code": self.country_code,
            "collection_code": self.collection_code,
            "year": self.year,
            "number": self.number,
            "official_name": self.official_name,
            "lawyer_title": self.lawyer_title,
            "publication_date": self.publication_date,
            "effective_from": self.effective_from,
            "version_token": self.version_token,
            "status": self.status,
            "applicable_to": self.applicable_to,
            "superseded_by_url": self.superseded_by_url,
            "parent_law_year": self.parent_law_year,
            "parent_law_number": self.parent_law_number,
            "source_url": self.source_url,
            "metadata": (
                self.metadata.normalized_payload()
                if self.metadata is not None
                else None
            ),
            "relations": [relation.normalized_payload() for relation in self.relations],
            "provisions": [
                {
                    "anchor": provision.anchor,
                    "heading": provision.heading,
                    "text": provision.text,
                }
                for provision in self.provisions
            ],
        }

    def version_checksum(self) -> str:
        payload = json.dumps(self.normalized_payload(), ensure_ascii=True, sort_keys=True)
        return sha256(payload.encode("utf-8")).hexdigest()


SlovLexLawSnapshot = LawSnapshot


@dataclass(frozen=True)
class StoredVersion:
    version_id: str
    state: str


@dataclass(frozen=True)
class LawSemanticCandidate:
    document_id: str
    version_id: str
    country_code: str
    collection_code: str
    law_year: int
    law_number: int
    official_name: str
    lawyer_title: str
    version_token: str
    effective_from: str
    embedding_model: str
    embedding_dimensions: int
    embedding_vector: str


@dataclass(frozen=True)
class LawSemanticSearchResult:
    document_id: str
    version_id: str
    country_code: str
    collection_code: str
    law_year: int
    law_number: int
    official_name: str
    lawyer_title: str
    version_token: str
    effective_from: str
    score: float


@dataclass(frozen=True)
class SyncSummary:
    processed: int = 0
    new_documents: int = 0
    new_versions: int = 0
    metadata_updates: int = 0
    skipped: int = 0

    def merge(self, other: "SyncSummary") -> "SyncSummary":
        return SyncSummary(
            processed=self.processed + other.processed,
            new_documents=self.new_documents + other.new_documents,
            new_versions=self.new_versions + other.new_versions,
            metadata_updates=self.metadata_updates + other.metadata_updates,
            skipped=self.skipped + other.skipped,
        )


@dataclass(frozen=True)
class CollectorProgress:
    country_code: str
    source_system: str
    last_collector_run_at: str | None
    last_processed_at: str | None
    last_processed_law_year: int | None
    last_processed_law_number: int | None
    next_probe_law_year: int
    next_probe_law_number: int

    @property
    def last_processed_law(self) -> str | None:
        if self.last_processed_law_year is None or self.last_processed_law_number is None:
            return None
        return format_law_identifier(
            year=self.last_processed_law_year,
            number=self.last_processed_law_number,
        )

    @property
    def next_probe_law(self) -> str:
        return format_law_identifier(
            year=self.next_probe_law_year,
            number=self.next_probe_law_number,
        )

    def evolve(self, **changes: object) -> "CollectorProgress":
        return replace(self, **changes)


@dataclass(frozen=True)
class UpdateCheckItem:
    document_key: str
    country_code: str
    collection_code: str
    year: int
    number: int
    version_token: str
    has_update: bool
    reason: str


@dataclass(frozen=True)
class UpdateCheckPlan:
    checked_items: int
    items_with_updates: int
    items: tuple[UpdateCheckItem, ...]


def format_law_identifier(*, year: int, number: int) -> str:
    return f"{number}/{year}"
