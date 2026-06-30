from __future__ import annotations

import logging
import re
from collections.abc import Callable, Iterable

from .domain import CourtDecisionRecord, CourtDecisionSyncSummary
from .infosud_source import InfoSudSourceClient
from .postgres_store import PostgresCourtDecisionStore

ProgressLogger = Callable[[str], None]


class CourtDecisionCollectorService:
    def __init__(
        self,
        *,
        store: PostgresCourtDecisionStore,
        source: InfoSudSourceClient | None = None,
        progress_logger: ProgressLogger | None = None,
    ) -> None:
        self.store = store
        self.source = source
        self.progress_logger = progress_logger or (lambda message: logging.info(message))

    def sync_records(self, records: Iterable[CourtDecisionRecord]) -> CourtDecisionSyncSummary:
        processed = 0
        created = 0
        updated = 0
        unchanged = 0
        last_source_guid = ""
        last_label = ""
        for record in records:
            label = record.ecli or record.file_number or record.case_number or record.source_guid
            decision_number = _decision_number(record)
            decision_year = _decision_year(record)
            self.progress_logger(
                "processing_judicial_decision "
                f"source_guid={record.source_guid} number={decision_number} year={decision_year} "
                f"status=processing court={record.court_name} label={label}"
            )
            stored = self.store.upsert_decision(record)
            processed += 1
            last_source_guid = record.source_guid
            last_label = label
            if stored.state == "created":
                created += 1
            elif stored.state == "updated":
                updated += 1
            else:
                unchanged += 1
            self.progress_logger(
                "processed_judicial_decision "
                f"source_guid={record.source_guid} number={decision_number} year={decision_year} "
                f"status={stored.state} decision_id={stored.decision_id}"
            )
        return CourtDecisionSyncSummary(
            processed=processed,
            created=created,
            updated=updated,
            unchanged=unchanged,
            last_source_guid=last_source_guid,
            last_label=last_label,
        )

    def sync_live_page(self, *, page: int = 0, size: int = 25) -> CourtDecisionSyncSummary:
        if self.source is None:
            raise ValueError("InfoSud source client is required for live sync")
        refs = self.source.list_decisions(page=page, size=size)
        records: list[CourtDecisionRecord] = []
        for ref in refs:
            self.progress_logger(f"fetching_decision source_guid={ref.guid} label={ref.label}")
            records.append(self.source.get_decision(ref.guid))
        return self.sync_records(records)


def _decision_number(record: CourtDecisionRecord) -> str:
    return record.file_number or record.case_number or record.ecli or record.source_guid


def _decision_year(record: CourtDecisionRecord) -> str:
    if record.issue_date:
        match = re.search(r"\b(19|20)\d{2}\b", record.issue_date)
        if match:
            return match.group(0)
    for value in (record.file_number, record.ecli, record.indexed_at, record.update_date):
        match = re.search(r"\b(19|20)\d{2}\b", value)
        if match:
            return match.group(0)
    return "unknown"
