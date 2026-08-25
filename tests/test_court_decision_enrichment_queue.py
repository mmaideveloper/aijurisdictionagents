from __future__ import annotations

from pathlib import Path

from services.court_decision_collector.config import CourtDecisionCollectorConfig
from services.court_decision_collector.enrichment_queue import BackgroundCourtDecisionEnricher
from services.court_decision_collector.postgres_store import (
    CourtDecisionEnrichmentWorkItem,
    ExpiredEnrichmentArtifact,
)
from services.court_decision_collector.pseudonymization import UnsafePseudonymizationError


def _config(monkeypatch, tmp_path: Path, *, enabled: bool = True) -> CourtDecisionCollectorConfig:
    monkeypatch.setenv("COURT_DECISIONS_DB_CLOUD", "postgresql://localhost/test")
    monkeypatch.setenv("COURT_DECISIONS_STORAGE_LOCAL", str(tmp_path))
    monkeypatch.setenv("COURT_DECISIONS_ENRICHMENT_ENABLED", str(enabled).lower())
    monkeypatch.setenv("COURT_DECISIONS_ENRICHMENT_CYCLE_LIMIT", "2")
    monkeypatch.setenv("COURT_DECISIONS_ENRICHMENT_CANDIDATE_LIMIT", "3")
    monkeypatch.setenv("COURT_DECISIONS_ENRICHMENT_RATE_DELAY_SECONDS", "0")
    monkeypatch.setenv("COURT_DECISIONS_ENRICHMENT_MIN_FREE_DISK_BYTES", "100")
    return CourtDecisionCollectorConfig.from_env()


class FakeStore:
    def __init__(self, items: list[CourtDecisionEnrichmentWorkItem] | None = None) -> None:
        self.items = list(items or [])
        self.paused = False
        self.enqueued = 0
        self.completed: list[str] = []
        self.retried: list[str] = []
        self.quarantined: list[str] = []
        self.expired: list[ExpiredEnrichmentArtifact] = []
        self.cleared: list[tuple[str, bool, bool]] = []

    def enrichment_is_paused(self, *, source_system: str) -> bool:
        assert source_system == "infosud"
        return self.paused

    def enqueue_recent_enrichment_candidates(self, **_kwargs) -> int:
        return self.enqueued

    def claim_next_enrichment(self, *, lease_seconds: int):
        assert lease_seconds >= 30
        return self.items.pop(0) if self.items else None

    def complete_enrichment_work(self, item) -> bool:
        self.completed.append(item.version_id)
        return True

    def retry_enrichment_work(self, item, *, error_type: str, backoff_seconds: int) -> str:
        assert error_type and backoff_seconds >= 0
        self.retried.append(item.version_id)
        return "dead_letter" if item.attempt_count >= item.max_attempts else "retryable"

    def quarantine_enrichment_work(self, item, *, error_type: str) -> None:
        assert error_type == "UnsafePseudonymizationError"
        self.quarantined.append(item.version_id)

    def expired_enrichment_artifacts(self, *, raw_before: str, pdf_before: str):
        assert raw_before.endswith("Z") and pdf_before.endswith("Z")
        return self.expired

    def clear_expired_enrichment_artifact(
        self, *, version_id: str, clear_raw: bool, clear_pdf: bool
    ) -> None:
        self.cleared.append((version_id, clear_raw, clear_pdf))


class FakeEnricher:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls: list[tuple[str, str]] = []

    def enrich_source_url(self, source_url: str, *, priority_class: str):
        self.calls.append((source_url, priority_class))
        if self.error:
            raise self.error
        return object()


def _item(*, attempt_count: int = 1, max_attempts: int = 3) -> CourtDecisionEnrichmentWorkItem:
    return CourtDecisionEnrichmentWorkItem(
        version_id="version-1",
        decision_id="decision-1",
        source_url="https://obcan.justice.sk/example",
        priority_class="user_requested",
        lease_token="lease-1",
        attempt_count=attempt_count,
        max_attempts=max_attempts,
    )


def test_background_enrichment_is_fail_closed_when_disabled(monkeypatch, tmp_path: Path) -> None:
    store = FakeStore([_item()])
    summary = BackgroundCourtDecisionEnricher(
        store=store,
        enricher=FakeEnricher(),
        config=_config(monkeypatch, tmp_path, enabled=False),
    ).run_cycle()
    assert summary.status == "disabled"
    assert store.items


def test_cycle_processes_bounded_user_priority_work(monkeypatch, tmp_path: Path) -> None:
    store = FakeStore([_item()])
    store.enqueued = 3
    enricher = FakeEnricher()
    summary = BackgroundCourtDecisionEnricher(
        store=store,
        enricher=enricher,
        config=_config(monkeypatch, tmp_path),
        sleep_fn=lambda _seconds: None,
        free_disk_fn=lambda _path: 1_000,
    ).run_cycle()
    assert summary.processed == 1 and summary.ready == 1
    assert store.completed == ["version-1"]
    assert enricher.calls == [("https://obcan.justice.sk/example", "user_requested")]


def test_cycle_quarantines_unsafe_public_derivative(monkeypatch, tmp_path: Path) -> None:
    store = FakeStore([_item()])
    summary = BackgroundCourtDecisionEnricher(
        store=store,
        enricher=FakeEnricher(UnsafePseudonymizationError("unsafe")),
        config=_config(monkeypatch, tmp_path),
        sleep_fn=lambda _seconds: None,
        free_disk_fn=lambda _path: 1_000,
    ).run_cycle()
    assert summary.quarantined == 1
    assert store.quarantined == ["version-1"]


def test_cycle_dead_letters_after_max_attempts(monkeypatch, tmp_path: Path) -> None:
    store = FakeStore([_item(attempt_count=3, max_attempts=3)])
    summary = BackgroundCourtDecisionEnricher(
        store=store,
        enricher=FakeEnricher(RuntimeError("synthetic")),
        config=_config(monkeypatch, tmp_path),
        sleep_fn=lambda _seconds: None,
        free_disk_fn=lambda _path: 1_000,
    ).run_cycle()
    assert summary.dead_letter == 1
    assert store.retried == ["version-1"]


def test_disk_guard_claims_no_work(monkeypatch, tmp_path: Path) -> None:
    store = FakeStore([_item()])
    summary = BackgroundCourtDecisionEnricher(
        store=store,
        enricher=FakeEnricher(),
        config=_config(monkeypatch, tmp_path),
        free_disk_fn=lambda _path: 99,
    ).run_cycle()
    assert summary.status == "disk_guard" and store.items


def test_retention_deletes_only_pdf_below_configured_root(monkeypatch, tmp_path: Path) -> None:
    pdf = tmp_path / "decision" / "version" / "decision.pdf"
    pdf.parent.mkdir(parents=True)
    pdf.write_bytes(b"synthetic")
    store = FakeStore()
    store.expired = [
        ExpiredEnrichmentArtifact("version-1", str(pdf), True, True)
    ]
    result = BackgroundCourtDecisionEnricher(
        store=store,
        enricher=FakeEnricher(),
        config=_config(monkeypatch, tmp_path),
    ).apply_retention()
    assert result == {"raw_cleared": 1, "pdf_cleared": 1, "rejected_pdf_paths": 0}
    assert not pdf.exists()
    assert store.cleared == [("version-1", True, True)]
