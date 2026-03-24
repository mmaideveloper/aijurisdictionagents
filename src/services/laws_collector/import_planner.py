from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from .config import LawsCollectorConfig


@dataclass(frozen=True)
class ImportWindow:
    stage: str
    start_date: date
    end_date: date
    blocked_by: str | None = None


@dataclass(frozen=True)
class ImportPlan:
    windows: tuple[ImportWindow, ...]

    @property
    def active_window(self) -> ImportWindow | None:
        for window in self.windows:
            if window.blocked_by is None:
                return window
        return None


class SlovLexImportPlanner:
    """Plans SlovLex import windows for Slovakia backfills."""

    def __init__(self, *, config: LawsCollectorConfig) -> None:
        self.config = config

    def build_plan(self, *, today: date | None = None, initial_window_complete: bool = False) -> ImportPlan:
        current_day = today or date.today()
        initial_window = ImportWindow(
            stage="initial_2025_to_today",
            start_date=self.config.initial_import_from,
            end_date=current_day,
        )

        historical_end = self.config.initial_import_from - timedelta(days=1)
        historical_window = ImportWindow(
            stage="historical_1946_to_2024",
            start_date=self.config.historical_import_from,
            end_date=historical_end,
            blocked_by=None if initial_window_complete else initial_window.stage,
        )
        return ImportPlan(windows=(initial_window, historical_window))
