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

def test_node_identity_isolated_between_parallel_requests_and_reset_after_failure():
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from aijurisdictionagents.correlation import node_execution_scope, current_node_execution
    barrier = Barrier(2)
    def run(identity):
        try:
            with node_execution_scope(run_id=identity, node_id='review', occurrence_id=identity):
                barrier.wait(timeout=5)
                assert current_node_execution()['workflow_run_id'] == identity
                raise RuntimeError('synthetic')
        except RuntimeError:
            assert current_node_execution() == {}
        return identity
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert set(pool.map(run, ['first', 'second'])) == {'first', 'second'}
