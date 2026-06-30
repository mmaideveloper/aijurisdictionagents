from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json


@dataclass(frozen=True)
class CourtDecisionRecord:
    source_system: str
    source_guid: str
    court_name: str
    court_type: str
    decision_form: str
    nature: str
    file_number: str
    case_number: str
    ecli: str
    issue_date: str
    indexed_at: str
    update_date: str
    source_url: str
    raw_text: str
    pseudonymized_text: str
    metadata: dict[str, object]

    @property
    def public_text(self) -> str:
        return self.pseudonymized_text or self.raw_text

    def normalized_payload(self) -> dict[str, object]:
        return {
            "source_system": self.source_system,
            "source_guid": self.source_guid,
            "court_name": self.court_name,
            "court_type": self.court_type,
            "decision_form": self.decision_form,
            "nature": self.nature,
            "file_number": self.file_number,
            "case_number": self.case_number,
            "ecli": self.ecli,
            "issue_date": self.issue_date,
            "indexed_at": self.indexed_at,
            "update_date": self.update_date,
            "source_url": self.source_url,
            "raw_text_checksum": sha256(self.raw_text.encode("utf-8")).hexdigest(),
            "pseudonymized_text_checksum": sha256(self.public_text.encode("utf-8")).hexdigest(),
            "metadata": self.metadata,
        }

    def version_checksum(self) -> str:
        payload = json.dumps(self.normalized_payload(), ensure_ascii=True, sort_keys=True)
        return sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class StoredCourtDecision:
    decision_id: str
    version_id: str
    state: str


@dataclass(frozen=True)
class CourtDecisionSyncSummary:
    processed: int = 0
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    last_source_guid: str = ""
    last_label: str = ""

    def merge(self, other: "CourtDecisionSyncSummary") -> "CourtDecisionSyncSummary":
        return CourtDecisionSyncSummary(
            processed=self.processed + other.processed,
            created=self.created + other.created,
            updated=self.updated + other.updated,
            unchanged=self.unchanged + other.unchanged,
            last_source_guid=other.last_source_guid or self.last_source_guid,
            last_label=other.last_label or self.last_label,
        )


@dataclass(frozen=True)
class CourtDecisionSearchResult:
    decision_id: str
    version_id: str
    source_guid: str
    court_name: str
    court_type: str
    file_number: str
    case_number: str
    ecli: str
    issue_date: str
    source_url: str
    snippet: str
    score: float
