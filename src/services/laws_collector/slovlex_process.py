from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
import time
from typing import Callable, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .config import LawsCollectorConfig
from .domain import CollectorProgress
from .domain import LawSnapshot
from .import_planner import ImportTarget, SlovLexImportPlanner
from .slovlex_live_source import SlovLexLiveSnapshotLoader


class CollectorProgressStore(Protocol):
    def get_or_create_collector_progress(
        self,
        *,
        country_code: str,
        source_system: str,
        initial_year: int,
    ) -> CollectorProgress: ...

    def save_collector_progress(self, progress: CollectorProgress) -> None: ...


class LiveSnapshotLoader(Protocol):
    def load_snapshot(self, *, target: ImportTarget, timeout_seconds: float = 12.0) -> LawSnapshot: ...


class LiveIngestService(Protocol):
    def sync(self, snapshots: tuple[LawSnapshot, ...]): ...


@dataclass(frozen=True)
class SlovLexProbeResult:
    target: ImportTarget
    exists: bool
    status_code: int | None
    url: str


@dataclass(frozen=True)
class SequentialImportSummary:
    probes: int
    laws_found: int
    failed_laws: int
    years_advanced: int
    stopped_on_current_year_gap: bool
    last_checked_law: str | None
    last_processed_law: str | None
    next_law_to_check: str
    last_collector_run_at: str | None
    last_processed_at: str | None
    first_found_url: str | None = None
    stopped_due_to_max_running_time: bool = False


class SlovLexSequentialImportRunner:
    def __init__(
        self,
        *,
        config: LawsCollectorConfig,
        store: CollectorProgressStore,
        planner: SlovLexImportPlanner | None = None,
        service: LiveIngestService | None = None,
        snapshot_loader: LiveSnapshotLoader | None = None,
        monotonic_time_provider: Callable[[], float] = time.monotonic,
    ) -> None:
        self.config = config
        self.store = store
        self.planner = planner or SlovLexImportPlanner(config=config)
        self.service = service
        self.snapshot_loader = snapshot_loader or SlovLexLiveSnapshotLoader()
        self._monotonic_time = monotonic_time_provider

    def get_progress(self) -> CollectorProgress:
        return self.store.get_or_create_collector_progress(
            country_code=self.config.country_code,
            source_system="slov-lex",
            initial_year=self.planner.initial_year,
        )

    def run(
        self,
        *,
        max_probes: int = 25,
        today: date | None = None,
        timeout_seconds: float = 12.0,
        max_running_seconds: float = 0,
    ) -> SequentialImportSummary:
        if max_probes < 1:
            raise ValueError("max_probes must be >= 1")
        if max_running_seconds < 0:
            raise ValueError("max_running_seconds must be >= 0")

        current_day = today or date.today()
        progress = self.get_progress()
        probes = 0
        laws_found = 0
        failed_laws = 0
        years_advanced = 0
        stopped_on_current_year_gap = False
        stopped_due_to_max_running_time = False
        last_checked_law: str | None = None
        first_found_url: str | None = None
        started_at = self._monotonic_time()

        while probes < max_probes:
            if max_running_seconds > 0 and (self._monotonic_time() - started_at) >= max_running_seconds:
                stopped_due_to_max_running_time = True
                _log(
                    f"stopped due to max running time country={self.config.country_code} "
                    f"elapsed_seconds={self._monotonic_time() - started_at:.1f} "
                    f"max_running_seconds={max_running_seconds:.1f}"
                )
                break
            plan = self.planner.build_plan(progress=progress, today=current_day)
            target = plan.next_target
            probe = self._probe_target(target=target, timeout_seconds=timeout_seconds)
            probes += 1
            last_checked_law = target.law_id
            observed_at = _now_iso()

            if probe.exists:
                if max_running_seconds > 0 and (self._monotonic_time() - started_at) >= max_running_seconds:
                    stopped_due_to_max_running_time = True
                    _log(
                        f"stopped before ingest due to max running time country={self.config.country_code} "
                        f"law={target.law_id} elapsed_seconds={self._monotonic_time() - started_at:.1f} "
                        f"max_running_seconds={max_running_seconds:.1f}"
                    )
                    break
                _log(
                    f"start processing country={self.config.country_code} "
                    f"law={target.law_id} source={probe.url}"
                )
                if self.service is not None:
                    try:
                        snapshot = self.snapshot_loader.load_snapshot(
                            target=target,
                            timeout_seconds=timeout_seconds,
                        )
                        self.service.sync((snapshot,))
                    except Exception as exc:
                        if _is_missing_resource_error(exc):
                            previous_year = progress.next_probe_law_year
                            progress, stopped_on_current_year_gap = self.planner.mark_missing(
                                progress,
                                target=target,
                                observed_at=observed_at,
                                today=current_day,
                            )
                            self.store.save_collector_progress(progress)
                            if progress.next_probe_law_year != previous_year:
                                years_advanced += 1
                            _log(
                                f"{target.law_id} does not exists, system imports all laws "
                                "and is up to date"
                            )
                            break
                        else:
                            failed_laws += 1
                            _log(
                                f"law processing failed country={self.config.country_code} "
                                f"law={target.law_id} source={probe.url} error={exc}"
                            )
                            progress = progress.evolve(
                                last_collector_run_at=observed_at,
                                next_probe_law_year=target.year,
                                next_probe_law_number=target.number,
                            )
                            self.store.save_collector_progress(progress)
                            stopped_on_current_year_gap = target.year >= current_day.year
                            break
                progress = self.planner.mark_processed(
                    progress,
                    target=target,
                    processed_at=observed_at,
                )
                self.store.save_collector_progress(progress)
                laws_found += 1
                if first_found_url is None:
                    first_found_url = probe.url
                continue

            previous_year = progress.next_probe_law_year
            progress, stopped_on_current_year_gap = self.planner.mark_missing(
                progress,
                target=target,
                observed_at=observed_at,
                today=current_day,
            )
            self.store.save_collector_progress(progress)
            if progress.next_probe_law_year != previous_year:
                years_advanced += 1
            if stopped_on_current_year_gap:
                break

        final_plan = self.planner.build_plan(progress=progress, today=current_day)
        if laws_found == 0:
            _log(
                f"No new laws for {self.config.country_code}, "
                f"last processed law {progress.last_processed_law or 'none'} "
                f"at {progress.last_processed_at or 'n/a'}"
            )
        return SequentialImportSummary(
            probes=probes,
            laws_found=laws_found,
            failed_laws=failed_laws,
            years_advanced=years_advanced,
            stopped_on_current_year_gap=stopped_on_current_year_gap,
            last_checked_law=last_checked_law,
            last_processed_law=progress.last_processed_law,
            next_law_to_check=final_plan.next_target.law_id,
            last_collector_run_at=progress.last_collector_run_at,
            last_processed_at=progress.last_processed_at,
            first_found_url=first_found_url,
            stopped_due_to_max_running_time=stopped_due_to_max_running_time,
        )

    def _probe_target(self, *, target: ImportTarget, timeout_seconds: float) -> SlovLexProbeResult:
        request = Request(
            target.url,
            headers={"User-Agent": "aijurisdictionagents-slovlex-runner/1.0"},
        )
        try:
            with urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310 - controlled HTTPS URL
                status_code = int(getattr(response, "status", 200))
                return SlovLexProbeResult(
                    target=target,
                    exists=status_code == 200,
                    status_code=status_code,
                    url=target.url,
                )
        except HTTPError as exc:
            return SlovLexProbeResult(
                target=target,
                exists=False,
                status_code=exc.code,
                url=target.url,
            )
        except URLError as exc:
            raise RuntimeError(f"SlovLex probe failed for {target.url}: {exc}") from exc


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _is_missing_resource_error(error: Exception) -> bool:
    return "HTTP 404" in str(error)


def _log(message: str) -> None:
    print(f"[laws-collector] {message}", flush=True)
