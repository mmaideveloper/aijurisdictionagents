from __future__ import annotations

import logging
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
            self.progress_logger(
                "processing_decision "
                f"source_guid={record.source_guid} court={record.court_name} label={label}"
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
                "processed_decision "
                f"source_guid={record.source_guid} state={stored.state} decision_id={stored.decision_id}"
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
