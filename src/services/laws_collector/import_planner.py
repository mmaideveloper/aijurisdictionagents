from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from .config import LawsCollectorConfig
from .domain import CollectorProgress

SLOVAK_INITIAL_IMPORT_YEAR = 1993


@dataclass(frozen=True)
class ImportTarget:
    year: int
    number: int

    @property
    def law_id(self) -> str:
        return f"{self.number}/{self.year}"

    @property
    def url(self) -> str:
        return f"https://www.slov-lex.sk/pravne-predpisy/SK/ZZ/{self.year}/{self.number}/"


@dataclass(frozen=True)
class ImportPlan:
    current_year: int
    initial_year: int
    last_collector_run_at: str | None
    last_processed_at: str | None
    last_processed_law: str | None
    next_target: ImportTarget
    stop_when_missing_current_year: bool


class SlovLexImportPlanner:
    """Plans sequential Slov-Lex probing by law number/year for Slovakia."""

    def __init__(self, *, config: LawsCollectorConfig) -> None:
        self.config = config

    @property
    def initial_year(self) -> int:
        return SLOVAK_INITIAL_IMPORT_YEAR

    def initial_progress(self) -> CollectorProgress:
        return CollectorProgress(
            country_code=self.config.country_code,
            source_system="slov-lex",
            last_collector_run_at=None,
            last_processed_at=None,
            last_processed_law_year=None,
            last_processed_law_number=None,
            next_probe_law_year=self.initial_year,
            next_probe_law_number=1,
        )

    def build_plan(
        self,
        *,
        progress: CollectorProgress | None = None,
        today: date | None = None,
    ) -> ImportPlan:
        current_day = today or date.today()
        state = progress or self.initial_progress()
        next_target = ImportTarget(
            year=state.next_probe_law_year,
            number=state.next_probe_law_number,
        )
        return ImportPlan(
            current_year=current_day.year,
            initial_year=self.initial_year,
            last_collector_run_at=state.last_collector_run_at,
            last_processed_at=state.last_processed_at,
            last_processed_law=state.last_processed_law,
            next_target=next_target,
            stop_when_missing_current_year=next_target.year >= current_day.year,
        )

    def mark_processed(
        self,
        progress: CollectorProgress,
        *,
        target: ImportTarget,
        processed_at: str,
    ) -> CollectorProgress:
        return progress.evolve(
            last_collector_run_at=processed_at,
            last_processed_at=processed_at,
            last_processed_law_year=target.year,
            last_processed_law_number=target.number,
            next_probe_law_year=target.year,
            next_probe_law_number=target.number + 1,
        )

    def mark_missing(
        self,
        progress: CollectorProgress,
        *,
        target: ImportTarget,
        observed_at: str,
        today: date | None = None,
    ) -> tuple[CollectorProgress, bool]:
        current_year = (today or date.today()).year
        if target.year < current_year:
            return (
                progress.evolve(
                    last_collector_run_at=observed_at,
                    next_probe_law_year=target.year + 1,
                    next_probe_law_number=1,
                ),
                False,
            )

        return (
            progress.evolve(
                last_collector_run_at=observed_at,
                next_probe_law_year=target.year,
                next_probe_law_number=target.number,
            ),
            True,
        )
