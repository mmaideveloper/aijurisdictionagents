from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.chat import api
from aijurisdictionagents.correlation import current_correlation_context


@pytest.mark.parametrize("fail", [False, True])
def test_worker_has_distinct_identity_and_terminal_evidence(monkeypatch, fail):
    contexts = []
    events = []

    class ImmediateThread:
        def __init__(self, *, target, daemon):
            self.target = target

        def start(self):
            self.target()

    def sink(context, component, stage, status, payload):
        events.append((context, status))

    def target():
        contexts.append(current_correlation_context())
        if fail:
            raise RuntimeError("synthetic failure")

    monkeypatch.setattr(api, "Thread", ImmediateThread)
    monkeypatch.setattr(api, "debug_event_sink", sink)
    session = SimpleNamespace(id="synthetic-session", correlation_id="synthetic-correlation")
    if fail:
        with pytest.raises(RuntimeError):
            api._start_session_worker(session=session, request_id="http-parent", target=target)
    else:
        api._start_session_worker(session=session, request_id="http-parent", target=target)
    assert contexts[0].request_id != "http-parent"
    assert contexts[0].parent_request_id == "http-parent"
    assert [status for _, status in events] == ["started", "failed" if fail else "completed"]
    assert current_correlation_context().request_id == ""


@pytest.mark.parametrize("parent,expected", [("browser-parent", "browser-parent"), ("invalid parent", "")])
def test_http_parent_header_is_bounded_and_labeled_unverified(monkeypatch, parent, expected):
    import app.main as main

    captured = []
    monkeypatch.setattr(main, "debug_event_sink", lambda context, *args: captured.append((context, args)))
    response = TestClient(main.app).get("/synthetic-missing-route", headers={
        "x-correlation-id": "synthetic-correlation", "x-request-id": "http-request",
        "x-parent-request-id": parent,
    })
    assert response.status_code == 404
    assert captured
    assert all(context.parent_request_id == expected for context, _ in captured)
    assert captured[0][1][-1]["parent_link_source"] == ("request_header" if expected else "none")
