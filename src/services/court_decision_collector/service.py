from __future__ import annotations

import logging
import re
import time
from collections.abc import Callable, Iterable
from datetime import date, datetime, timezone
from hashlib import sha256
from typing import Protocol

from .domain import CourtDecisionRecord, CourtDecisionSyncSummary
from .infosud_source import InfoSudDecisionPage, InfoSudDecisionRef
from .postgres_store import CourtDecisionSchedulerState, PostgresCourtDecisionStore

ProgressLogger = Callable[[str], None]
SleepFunction = Callable[[float], None]
UtcNowFunction = Callable[[], datetime]
CycleHook = Callable[[], object]


class CourtDecisionSource(Protocol):
    source_system: str

    def list_decisions(self, *, page: int = 0, size: int = 25) -> list[InfoSudDecisionRef]: ...

    def list_decision_page(self, *, page: int = 0, size: int = 25) -> InfoSudDecisionPage: ...

    def get_decision(self, guid: str) -> CourtDecisionRecord: ...


class CourtDecisionCollectorService:
    def __init__(
        self,
        *,
        store: PostgresCourtDecisionStore,
        source: CourtDecisionSource | None = None,
        progress_logger: ProgressLogger | None = None,
        utc_now: UtcNowFunction | None = None,
        enrichment_auto_queue: bool = False,
        enrichment_max_attempts: int = 3,
        enrichment_cycle_hook: CycleHook | None = None,
    ) -> None:
        self.store = store
        self.source = source
        self.progress_logger = progress_logger or (lambda message: logging.info(message))
        self.utc_now = utc_now or (lambda: datetime.now(timezone.utc))
        self.enrichment_auto_queue = enrichment_auto_queue
        self.enrichment_max_attempts = enrichment_max_attempts
        self.enrichment_cycle_hook = enrichment_cycle_hook

    def sync_records(
        self,
        records: Iterable[CourtDecisionRecord],
        *,
        work_class: str = "manual",
    ) -> CourtDecisionSyncSummary:
        summary = CourtDecisionSyncSummary()
        for record in records:
            reference_hash = _reference_hash(record.source_guid)
            self.progress_logger(
                "processing_judicial_decision "
                f"reference_hash={reference_hash} year={_decision_year(record)} "
                f"work_class={work_class} status=processing"
            )
            stored = self.store.upsert_decision(record, work_class=work_class)
            if self.enrichment_auto_queue and stored.state in {"created", "updated"}:
                enqueue = getattr(self.store, "enqueue_enrichment", None)
                if callable(enqueue):
                    enqueue(
                        decision_id=stored.decision_id,
                        version_id=stored.version_id,
                        priority_class="recent",
                        max_attempts=self.enrichment_max_attempts,
                    )
            summary = summary.merge(
                CourtDecisionSyncSummary(
                    processed=1,
                    created=1 if stored.state == "created" else 0,
                    updated=1 if stored.state == "updated" else 0,
                    unchanged=1 if stored.state == "unchanged" else 0,
                    last_source_guid=record.source_guid,
                    last_label=reference_hash,
                )
            )
            self.progress_logger(
                "processed_judicial_decision "
                f"reference_hash={reference_hash} work_class={work_class} status={stored.state}"
            )
        return summary

    def sync_live_page(self, *, page: int = 0, size: int = 25) -> CourtDecisionSyncSummary:
        source = self._required_source()
        refs = source.list_decisions(page=page, size=size)
        return self.sync_records((source.get_decision(ref.guid) for ref in refs))

    def run_priority_cycle(
        self,
        *,
        page_size: int = 25,
        daily_new_limit: int = 10000,
        discovery_overlap_pages: int = 2,
        backfill_pages_per_cycle: int = 10,
        max_decisions: int = 0,
    ) -> CourtDecisionSyncSummary:
        source = self._required_source()
        if page_size < 1 or daily_new_limit < 1:
            raise ValueError("page_size and daily_new_limit must be >= 1")
        utc_day = self.utc_now().astimezone(timezone.utc).date()
        first_page = source.list_decision_page(page=0, size=page_size)
        state = self.store.ensure_scheduler_state(
            source_system=source.source_system,
            source_total=first_page.total,
            source_updated_at=first_page.source_updated_at,
            page_size=page_size,
            daily_new_limit=daily_new_limit,
            utc_day=utc_day,
            overlap_pages=discovery_overlap_pages,
        )
        if first_page.total < state.discovered_source_total:
            self.store.record_checkpoint_failure(
                source_system=source.source_system,
                status="degraded_source_total_regressed",
            )
            self.progress_logger(
                "collector_checkpoint_failure reason=source_total_regressed "
                f"previous_total={state.discovered_source_total} observed_total={first_page.total}"
            )
            return CourtDecisionSyncSummary()

        self._discover_new_work(
            first_page=first_page,
            state=state,
            page_size=page_size,
            overlap_pages=discovery_overlap_pages,
        )
        summary = self._drain_work(
            work_class="new",
            utc_day=utc_day,
            daily_new_limit=daily_new_limit,
            max_items=max_decisions,
        )
        pending_new = self.store.pending_work_count(
            source_system=source.source_system,
            work_class="new",
        )
        state = self.store.get_scheduler_state(source_system=source.source_system)
        if pending_new:
            reason = "daily_quota_exhausted" if state.quota_remaining == 0 else "new_backlog_pending"
            self.progress_logger(
                "new_priority_paused "
                f"reason={reason} pending_new={pending_new} quota_used={state.quota_used} "
                f"daily_new_limit={state.daily_new_limit}"
            )
            return summary
        if max_decisions and summary.processed >= max_decisions:
            return summary

        for _ in range(backfill_pages_per_cycle):
            state = self.store.get_scheduler_state(source_system=source.source_system)
            page_number = state.backfill_next_page
            page = first_page if page_number == 0 else source.list_decision_page(
                page=page_number,
                size=page_size,
            )
            page_count = max(1, (first_page.total + page_size - 1) // page_size)
            if first_page.total > 0 and page_number < page_count and not page.refs:
                self.store.record_checkpoint_failure(
                    source_system=source.source_system,
                    status="degraded_backfill_page_missing",
                )
                self.progress_logger(
                    "collector_checkpoint_failure reason=backfill_page_missing "
                    f"page={page_number} expected_pages={page_count}"
                )
                return summary
            self._enqueue_page(page=page, work_class="backfill", quota_boundary=0)
            remaining = 0 if not max_decisions else max(0, max_decisions - summary.processed)
            if max_decisions and remaining == 0:
                return summary
            page_summary = self._drain_work(
                work_class="backfill",
                utc_day=utc_day,
                daily_new_limit=daily_new_limit,
                max_items=remaining,
            )
            summary = summary.merge(page_summary)
            if max_decisions and self.store.pending_work_count(
                source_system=source.source_system,
                work_class="backfill",
            ):
                return summary
            self.store.advance_backfill_checkpoint(
                source_system=source.source_system,
                source_total=first_page.total,
                page_size=page_size,
                page=page_number,
                wrote_data=bool(page_summary.created or page_summary.updated),
            )
            if page_number + 1 >= page_count:
                break
            if max_decisions and summary.processed >= max_decisions:
                break
        return summary

    def run_until_current(
        self,
        *,
        page_size: int = 25,
        max_pages: int = 0,
        stop_after_decisions: int = 0,
        cursor_kind: str = "priority_scheduler",
    ) -> CourtDecisionSyncSummary:
        del cursor_kind
        return self.run_priority_cycle(
            page_size=page_size,
            backfill_pages_per_cycle=max_pages or 1_000_000,
            max_decisions=stop_after_decisions,
        )

    def run_worker_loop(
        self,
        *,
        page_size: int = 25,
        poll_seconds: float = 3600,
        daily_new_limit: int = 10000,
        discovery_overlap_pages: int = 2,
        backfill_pages_per_cycle: int = 10,
        max_idle_cycles: int = 0,
        sleep_fn: SleepFunction = time.sleep,
    ) -> CourtDecisionSyncSummary:
        source = self._required_source()
        if poll_seconds < 0:
            raise ValueError("poll_seconds must be >= 0")
        total = CourtDecisionSyncSummary()
        idle_cycles = 0
        self.progress_logger(
            "collector_worker_started scheduler=priority_v2 "
            f"page_size={page_size} poll_seconds={poll_seconds:g} "
            f"daily_new_limit={daily_new_limit}"
        )
        while True:
            try:
                cycle = self.run_priority_cycle(
                    page_size=page_size,
                    daily_new_limit=daily_new_limit,
                    discovery_overlap_pages=discovery_overlap_pages,
                    backfill_pages_per_cycle=backfill_pages_per_cycle,
                )
                if self.enrichment_cycle_hook is not None:
                    self.enrichment_cycle_hook()
                total = total.merge(cycle)
                idle_cycles = idle_cycles + 1 if cycle.processed == 0 else 0
                state = self.store.get_scheduler_state(source_system=source.source_system)
                pending_new = self.store.pending_work_count(
                    source_system=source.source_system,
                    work_class="new",
                )
                self.progress_logger(
                    "waiting_for_new_judicial_decisions "
                    f"status={state.status} idle_cycles={idle_cycles} wait_seconds={poll_seconds:g} "
                    f"pending_new={pending_new} quota_remaining={state.quota_remaining}"
                )
                if max_idle_cycles and idle_cycles >= max_idle_cycles:
                    return total
                sleep_fn(poll_seconds)
            except Exception as exc:
                self.progress_logger(
                    "collector_worker_error "
                    f"status=error error_type={type(exc).__name__} message={_log_safe(str(exc))}"
                )
                sleep_fn(poll_seconds)

    def _discover_new_work(
        self,
        *,
        first_page: InfoSudDecisionPage,
        state: CourtDecisionSchedulerState,
        page_size: int,
        overlap_pages: int,
    ) -> None:
        source_metadata_changed = bool(
            first_page.source_updated_at
            and first_page.source_updated_at != state.source_updated_at
        )
        if first_page.total == state.discovered_source_total and not source_metadata_changed:
            return
        boundary = min(first_page.total, state.discovered_source_total)
        start_ordinal = max(0, boundary - overlap_pages * page_size)
        start_page = start_ordinal // page_size
        last_page = max(0, (first_page.total - 1) // page_size)
        for page_number in range(start_page, last_page + 1):
            page = first_page if page_number == 0 else self._required_source().list_decision_page(
                page=page_number,
                size=page_size,
            )
            self._enqueue_page(
                page=page,
                work_class="new",
                quota_boundary=start_ordinal,
            )
        self.store.save_discovery_checkpoint(
            source_system=state.source_system,
            source_total=first_page.total,
            source_updated_at=first_page.source_updated_at,
        )
        self.progress_logger(
            "new_work_discovered "
            f"previous_total={state.discovered_source_total} observed_total={first_page.total} "
            f"source_metadata_changed={str(source_metadata_changed).lower()} "
            f"start_page={start_page} end_page={last_page}"
        )

    def _enqueue_page(
        self,
        *,
        page: InfoSudDecisionPage,
        work_class: str,
        quota_boundary: int,
    ) -> None:
        entries = [
            (ref.guid, page.page * page.size + index, page.page * page.size + index >= quota_boundary)
            for index, ref in enumerate(page.refs)
        ]
        self.store.enqueue_work_page(
            source_system=self._required_source().source_system,
            work_class=work_class,
            source_page=page.page,
            entries=entries,
        )

    def _drain_work(
        self,
        *,
        work_class: str,
        utc_day: date,
        daily_new_limit: int,
        max_items: int,
    ) -> CourtDecisionSyncSummary:
        source = self._required_source()
        summary = CourtDecisionSyncSummary()
        while not max_items or summary.processed < max_items:
            if work_class == "new":
                state = self.store.get_scheduler_state(source_system=source.source_system)
                if state.quota_day != utc_day:
                    state = self.store.ensure_scheduler_state(
                        source_system=source.source_system,
                        source_total=state.discovered_source_total,
                        source_updated_at=state.source_updated_at,
                        page_size=1,
                        daily_new_limit=daily_new_limit,
                        utc_day=utc_day,
                        overlap_pages=1,
                    )
                if state.quota_remaining == 0:
                    break
            item = self.store.next_work_item(
                source_system=source.source_system,
                work_class=work_class,
            )
            if item is None:
                break
            try:
                record = source.get_decision(item.source_guid)
                item_summary = self.sync_records([record], work_class=work_class)
                self.store.complete_work_item(
                    item,
                    utc_day=utc_day,
                    count_quota=bool(item_summary.created or item_summary.updated),
                )
                summary = summary.merge(item_summary)
            except Exception as exc:
                self.store.mark_work_retry(item, error_type=type(exc).__name__)
                self.progress_logger(
                    "court_decision_work_retry "
                    f"reference_hash={_reference_hash(item.source_guid)} work_class={work_class} "
                    f"error_type={type(exc).__name__}"
                )
                raise
        return summary

    def _required_source(self) -> CourtDecisionSource:
        if self.source is None:
            raise ValueError("InfoSud source client is required for collector sync")
        return self.source


def _decision_year(record: CourtDecisionRecord) -> str:
    for value in (record.issue_date, record.indexed_at, record.update_date):
        match = re.search(r"\b(19|20)\d{2}\b", value)
        if match:
            return match.group(0)
    return "unknown"


def _reference_hash(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()[:16]


def _log_safe(value: str) -> str:
    return " ".join(value.split())[:240]
