from __future__ import annotations

from app import email_scheduler_job_main


def test_job_main_skips_when_disabled(monkeypatch) -> None:
    monkeypatch.setattr(email_scheduler_job_main, "configure_logging", lambda: None)
    monkeypatch.setattr(email_scheduler_job_main, "scheduler_enabled", lambda: False)

    class DisabledScheduler:
        @classmethod
        def from_env(cls):  # pragma: no cover - defensive assertion path
            raise AssertionError("Scheduler should not be created when disabled")

    monkeypatch.setattr(email_scheduler_job_main, "EmailScheduler", DisabledScheduler)

    assert email_scheduler_job_main.main() == 0


def test_job_main_processes_single_batch(monkeypatch) -> None:
    monkeypatch.setattr(email_scheduler_job_main, "configure_logging", lambda: None)
    monkeypatch.setattr(email_scheduler_job_main, "scheduler_enabled", lambda: True)

    class FakeSchedulerInstance:
        def __init__(self) -> None:
            self.limits: list[int] = []

        def run_once(self, *, limit: int = 50) -> int:
            self.limits.append(limit)
            return 3

    scheduler = FakeSchedulerInstance()

    class FakeScheduler:
        @classmethod
        def from_env(cls) -> FakeSchedulerInstance:
            return scheduler

    monkeypatch.setattr(email_scheduler_job_main, "EmailScheduler", FakeScheduler)

    assert email_scheduler_job_main.main() == 3
    assert scheduler.limits == [50]
