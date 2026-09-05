from aijurisdictionagents.correlation import (
    child_operation,
    correlation_headers,
    correlation_scope,
    current_correlation_context,
    record_debug_event,
)


def test_child_operation_keeps_session_correlation_and_links_parent() -> None:
    captured = []

    def sink(context, component, stage, status, payload) -> None:
        captured.append((context, component, stage, status, payload))

    with correlation_scope(
        correlation_id="corr-303",
        session_id="session-303",
        request_id="request-parent",
        debug_sink=sink,
    ):
        with child_operation(request_id="request-child") as child:
            record_debug_event("model", "completion", "started", {"model": "test"})
            assert correlation_headers() == {
                "x-correlation-id": "corr-303",
                "x-request-id": "request-child",
                "x-parent-request-id": "request-parent",
            }

    assert child.correlation_id == "corr-303"
    assert child.parent_request_id == "request-parent"
    assert captured[0][0].request_id == "request-child"
    assert current_correlation_context().correlation_id == ""
