from __future__ import annotations

import json

from scripts.server.export_system_status_metrics import _merge_local_runtime, _render_metrics
from scripts.server.write_system_status import _latest_laws_run_summary, _recent_error_lines


def test_laws_run_summary_parses_latest_execution() -> None:
    log_text = "\n".join(
        [
            "[2026-06-15T01:00:00Z] starting laws collector daily job",
            "[laws-collector] import_mode=zip entries_processed=10 processed=8 new_documents=7",
            "[2026-06-15T01:05:00Z] laws collector daily job finished",
            "[2026-06-16T01:00:00Z] starting laws collector daily job",
            "[laws-collector] import_mode=zip entries_processed=4 processed=3 new_documents=2",
            "[laws-collector] import_mode=zip_tail_probe laws_found=1 failed_laws=0",
        ]
    )

    assert _latest_laws_run_summary(log_text) == {
        "imported_laws": 3,
        "entries_processed": 4,
        "processed": 3,
    }


def test_recent_error_lines_are_sanitized_and_limited() -> None:
    log_text = "\n".join(
        [
            "[2026-06-16T01:00:00Z] failed url=postgresql://user:secret@db/app token=abc123",
            "[2026-06-16T01:01:00Z] ok",
        ]
    )

    errors = _recent_error_lines(log_text)

    assert errors == [
        {
            "timestamp": "2026-06-16T01:00:00Z",
            "message": "[2026-06-16T01:00:00Z] failed url=postgresql://user:***@db/app token=***",
        }
    ]


def test_exporter_renders_laws_runtime_and_recent_error_metrics() -> None:
    metrics = _render_metrics(
        {
            "status": "ok",
            "laws_collector": {
                "status": "ok",
                "runtime": {
                    "last_run_duration_seconds": 42,
                    "last_run_imported_laws": 3,
                    "last_run_entries_processed": 4,
                    "last_run_processed": 3,
                    "recent_errors": [
                        {
                            "timestamp": "2026-06-16T01:00:00Z",
                            "message": "failed import_key=monthly",
                        }
                    ],
                },
            },
        }
    )

    assert "jurisdigta_laws_runtime_duration_seconds 42.0" in metrics
    assert "jurisdigta_laws_runtime_imported_laws 3.0" in metrics
    assert "jurisdigta_laws_runtime_entries_processed 4.0" in metrics
    assert "jurisdigta_laws_runtime_processed 3.0" in metrics
    assert (
        'jurisdigta_laws_recent_error_info{index="1",timestamp="2026-06-16T01:00:00Z",'
        'message="failed import_key=monthly"} 1'
    ) in metrics


def test_exporter_merges_laws_runtime_from_local_status_file(monkeypatch, tmp_path) -> None:
    status_file = tmp_path / "system-status.json"
    status_file.write_text(
        json.dumps(
            {
                "apps": {
                    "laws_collector": {
                        "last_run_duration_seconds": 18,
                        "last_run_imported_laws": 2,
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("SYSTEM_STATUS_FILE", str(status_file))

    payload = _merge_local_runtime({"laws_collector": {"status": "ok", "runtime": None}})

    assert payload["laws_collector"]["runtime"]["last_run_duration_seconds"] == 18
    assert payload["laws_collector"]["runtime"]["last_run_imported_laws"] == 2
