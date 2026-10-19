"""Optional diagnostic failures must not log a private exception or its causal chain."""

from typing import Any

import pytest

from aijurisdictionagents.correlation import CorrelationContext
from app.debug_trace import debug_event_sink


def test_sink_failure_does_not_log_private_chained_exception(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture,
) -> None:
    from app.case_workflows import service

    def unavailable() -> Any:
        raise ValueError("synthetic private database diagnostic")

    monkeypatch.setattr(service, "get_case_workflow_service", unavailable)
    context = CorrelationContext(correlation_id="synthetic-correlation", request_id="synthetic-request")
    try:
        raise RuntimeError("synthetic private chat exception")
    except RuntimeError:
        debug_event_sink(context, "chat", "error", "failed", {"prompt": "synthetic private prompt"})

    assert "error_type=ValueError" in caplog.text
    assert "synthetic-correlation" in caplog.text and "synthetic-request" in caplog.text
    assert "synthetic private" not in caplog.text
    records = [record for record in caplog.records if record.name == "app.debug_trace"]
    assert len(records) == 1 and records[0].exc_info is None
