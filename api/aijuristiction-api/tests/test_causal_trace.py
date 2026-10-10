from app.causal_trace import build_causal_flow


def event(event_id, request, parent="", session="s1", **extra):
    return {"event_id": event_id, "request_id": request, "parent_request_id": parent,
            "session_id": session, "component": "model", "stage": "completion",
            "status": "completed", **extra}


def test_parallel_requests_retries_and_turns_are_not_linked_by_order():
    result = build_causal_flow([
        event("e1", "turn1"), event("e2", "child1", "turn1"),
        event("e3", "turn2"), event("e4", "child2", "turn1"),
        event("e5", "retry1", "turn1"), event("e6", "child1", "turn1"),
    ])
    assert result["edges"] == [
        {"from": "turn1", "to": "child1"}, {"from": "turn1", "to": "child2"},
        {"from": "turn1", "to": "retry1"},
    ]
    nodes = {node["id"]: node for node in result["nodes"]}
    assert len(nodes["child1"]["observations"]) == 2
    assert nodes["child2"]["root_request_id"] == "turn1"
    assert nodes["turn2"]["root_request_id"] == "turn2"


def test_missing_and_ambiguous_evidence_is_not_fabricated():
    result = build_causal_flow([
        event("e1", "orphan", "expired"), event("e2", ""),
        event("e3", "collision", session="s1"), event("e4", "collision", session="s2"),
        event("e5", "child", "collision"),
    ], truncated=True)
    assert result["edges"] == []
    assert result["unlinked_event_ids"] == ["e2"]
    assert result["completeness"] == "partial"
    assert "ambiguous_parent_identity" in result["evidence_gaps"]
    assert result["nodes"][0]["root_request_id"] is None


def test_cycles_do_not_hang_or_imply_a_root():
    result = build_causal_flow([event("e1", "a", "b"), event("e2", "b", "a")])
    assert result["edges"] == []
    assert "cyclic_parent_links" in result["evidence_gaps"]
    assert all(node["root_request_id"] is None for node in result["nodes"])


def test_projection_never_copies_payloads():
    result = build_causal_flow([event("e1", "r", payload={"prompt": "PRIVATE", "token": "SECRET"})])
    assert "PRIVATE" not in str(result)
    assert "SECRET" not in str(result)
    assert result["completeness"] == "recorded_evidence_only"
