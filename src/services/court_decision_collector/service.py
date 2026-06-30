from __future__ import annotations

import logging
import re
from collections.abc import Callable, Iterable
from typing import Protocol

from .domain import CourtDecisionRecord, CourtDecisionSyncSummary
from .infosud_source import InfoSudDecisionRef
from .postgres_store import PostgresCourtDecisionStore

ProgressLogger = Callable[[str], None]


class CourtDecisionSource(Protocol):
    source_system: str

    def list_decisions(self, *, page: int = 0, size: int = 25) -> list[InfoSudDecisionRef]:
        ...

    def get_decision(self, guid: str) -> CourtDecisionRecord:
        ...


class CourtDecisionCollectorService:
    def __init__(
        self,
        *,
        store: PostgresCourtDecisionStore,
        source: CourtDecisionSource | None = None,
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

    def run_until_current(
        self,
        *,
        page_size: int = 25,
        max_pages: int = 0,
        stop_after_decisions: int = 0,
        cursor_kind: str = "live_loop",
    ) -> CourtDecisionSyncSummary:
        if self.source is None:
            raise ValueError("InfoSud source client is required for loop sync")
        source_system = self.source.source_system
        cursor = self.store.get_import_state(source_system=source_system, cursor_kind=cursor_kind)
        last_successful_guid = cursor.last_source_guid
        cursor_seen = not last_successful_guid
        if last_successful_guid:
            self.progress_logger(
                "resume_state "
                f"source_system={source_system} cursor_kind={cursor_kind} "
                f"last_source_guid={last_successful_guid} status={cursor.status}"
            )
        summary = CourtDecisionSyncSummary()
        page = 0
        processed_this_run = 0
        while True:
            if max_pages and page >= max_pages:
                self.store.save_import_state(
                    source_system=source_system,
                    cursor_kind=cursor_kind,
                    last_source_guid=last_successful_guid,
                    status="paused_max_pages",
                )
                self.progress_logger(
                    "collector_loop_stopped "
                    f"reason=max_pages page={page} processed={summary.processed} "
                    f"last_source_guid={last_successful_guid}"
                )
                return summary
            refs = self.source.list_decisions(page=page, size=page_size)
            self.progress_logger(f"polling_decision_page page={page} size={page_size} count={len(refs)}")
            if not refs:
                self.store.save_import_state(
                    source_system=source_system,
                    cursor_kind=cursor_kind,
                    last_source_guid=last_successful_guid,
                    status="up_to_date",
                )
                self.progress_logger(
                    "collector_loop_stopped "
                    f"reason=no_new_decisions status=up_to_date processed={summary.processed} "
                    f"last_source_guid={last_successful_guid}"
                )
                return summary
            for ref in refs:
                if not cursor_seen:
                    self.progress_logger(
                        "skipping_processed_decision "
                        f"source_guid={ref.guid} resume_until={last_successful_guid}"
                    )
                    if ref.guid == last_successful_guid:
                        cursor_seen = True
                        self.progress_logger(f"resume_cursor_found source_guid={ref.guid}")
                    continue
                if ref.guid == last_successful_guid:
                    continue
                record = self.source.get_decision(ref.guid)
                item_summary = self.sync_records([record])
                summary = summary.merge(item_summary)
                last_successful_guid = record.source_guid
                processed_this_run += 1
                self.store.save_import_state(
                    source_system=source_system,
                    cursor_kind=cursor_kind,
                    last_source_guid=last_successful_guid,
                    status="running",
                )
                if stop_after_decisions and processed_this_run >= stop_after_decisions:
                    self.store.save_import_state(
                        source_system=source_system,
                        cursor_kind=cursor_kind,
                        last_source_guid=last_successful_guid,
                        status="stopped_mid_run",
                    )
                    self.progress_logger(
                        "collector_loop_stopped "
                        f"reason=stop_after_decisions status=stopped_mid_run "
                        f"processed={summary.processed} last_source_guid={last_successful_guid}"
                    )
                    return summary
            page += 1


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
