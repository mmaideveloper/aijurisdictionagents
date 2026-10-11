from app.decision_evidence import build_decision_evidence


def test_exact_run_and_event_join_keeps_repeated_nodes_separate():
    graph = {"runs": [{"workflow_run_id": "run-1", "occurrences": [
        {"event_id": "event-1", "node_id": "review"},
        {"event_id": "event-2", "node_id": "review"},
    ]}, {"workflow_run_id": "run-2", "occurrences": [{"event_id": "event-1"}]}]}
    evidence = build_decision_evidence([{"event_id": "event-1", "workflow_run_id": "run-1", "actor": "system", "decision": {"reason_code": "unresolved_placeholder"}}], graph)
    assert evidence["engine"] == "langgraph"
    occurrences = graph["runs"][0]["occurrences"]
    assert occurrences[0]["decision_evidence"]["reason_code"] == "unresolved_placeholder"
    assert "decision_evidence" not in occurrences[1]
    assert "decision_evidence" not in graph["runs"][1]["occurrences"][0]


def test_model_tag_does_not_turn_narrative_or_secret_into_summary():
    evidence = build_decision_evidence([{
        "event_id": "event-1", "actor": "model", "decision": {
            "reason_code": "sk-private-credential", "summary": "private case facts",
            "chain_of_thought": "hidden", "prompt": "ignore instructions",
        },
    }], {"runs": []})
    assert evidence["engine"] == "unknown"
    assert evidence["explanations"][0]["reason_code"] is None
    assert evidence["model_supplied_summary_status"] == "unavailable"
    for forbidden in ("sk-private", "private case", "hidden", "ignore instructions"):
        assert forbidden not in str(evidence)


def test_no_graph_is_unknown_not_not_applicable():
    evidence = build_decision_evidence([], {"runs": []})
    assert evidence["engine"] == "unknown"
    assert evidence["explanations"] == []

def test_execution_join_requires_run_node_and_occurrence_and_minimizes_fields():
    graph = {'runs': [{'workflow_run_id': 'run', 'occurrences': [
        {'node_id': 'review', 'occurrence_id': 'attempt-1'},
        {'node_id': 'review', 'occurrence_id': 'attempt-2'},
    ]}, {'workflow_run_id': 'other', 'occurrences': [{'node_id': 'review', 'occurrence_id': 'attempt-1'}]}]}
    build_decision_evidence([], graph, [{'event_id': 'event', 'request_id': 'request', 'component': 'validation', 'stage': 'check', 'status': 'passed', 'payload': {
        'node_execution': {'workflow_run_id': 'run', 'node_id': 'review', 'occurrence_id': 'attempt-1'},
        'validator_id': 'review-output', 'validator_version': '1', 'artifact_id': 'revision-2', 'prompt': 'secret private text',
    }}])
    first, second = graph['runs'][0]['occurrences']
    assert first['execution_evidence'][0]['artifact_id'] == 'revision-2'
    assert first['execution_evidence'][0]['request_id'] == 'request'
    assert second['execution_evidence_status'] == 'no_linked_evidence'
    assert not graph['runs'][1]['occurrences'][0]['execution_evidence']
    assert 'secret private text' not in str(graph)
