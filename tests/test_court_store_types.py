from contextlib import contextmanager
from datetime import date

import pytest

from services.court_decision_collector.postgres_store import PostgresCourtDecisionStore


def coverage_store(monkeypatch, row):
    store = PostgresCourtDecisionStore(connection_uri="unused-synthetic-config")

    class Connection:
        def execute(self, statement):
            assert "COUNT(*)" in statement
            return self

        def fetchone(self):
            return row

    @contextmanager
    def connect():
        yield Connection()

    monkeypatch.setattr(store, "_connect", connect)
    return store


def test_coverage_preserves_aggregate_counts_and_latest_date(monkeypatch):
    store = coverage_store(monkeypatch, {
        "published_decisions": 12, "latest_issue_date": date(2026, 10, 11), "enriched_versions": 3,
    })
    assert store.search_coverage() == {
        "published_decisions": 12, "latest_issue_date": "2026-10-11", "enriched_versions": 3,
    }


def test_empty_corpus_coverage_preserves_zero_counts_and_unknown_date(monkeypatch):
    store = coverage_store(monkeypatch, {
        "published_decisions": 0, "latest_issue_date": None, "enriched_versions": 0,
    })
    assert store.search_coverage() == {
        "published_decisions": 0, "latest_issue_date": "", "enriched_versions": 0,
    }


def test_missing_aggregate_row_fails_instead_of_inventing_coverage(monkeypatch):
    store = coverage_store(monkeypatch, None)
    with pytest.raises(RuntimeError, match="no aggregate row"):
        store.search_coverage()
