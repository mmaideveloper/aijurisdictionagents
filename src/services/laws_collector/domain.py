from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json


@dataclass(frozen=True)
class ProvisionRecord:
    anchor: str
    heading: str
    text: str


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
