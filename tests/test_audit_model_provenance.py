from dataclasses import replace
from types import SimpleNamespace

import pytest

from aijurisdictionagents.api_db import ApiDatabaseStore
from aijurisdictionagents.audit_model_provenance import route_provenance
from aijurisdictionagents.correlation import correlation_scope
from aijurisdictionagents.llm.base import execute_correlated_model_call
from aijurisdictionagents.llm.routing import get_routed_llm_client


def test_selected_policy_snapshot_survives_policy_update(tmp_path, monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    store = ApiDatabaseStore(db_path=tmp_path / "audit.sqlite3", blob_root=tmp_path / "blob")
    store.initialize()
    user = store.create_user(email="audit@example.invalid", password="synthetic-only", full_name="Synthetic")
    captured = []
    with correlation_scope(correlation_id="synthetic", request_id="turn-1", debug_sink=lambda *event: captured.append(event)):
        routed = get_routed_llm_client(store=store, user_id=user.user_id, task_type="legal_analysis")
    snapshot = routed.client._audit_route_provenance
    assert snapshot["reason_code"] == "policy_local"
    assert snapshot["policy_digest"]
    assert snapshot["provider_api_version"] != snapshot["model_alias"]
    assert captured[0][1:4] == ("model_router", "route_selected", "observed")
    assert routed.route.policy is not None
    changed = replace(routed.route, policy=replace(routed.route.policy, priority=999))
    assert route_provenance(changed)["policy_digest"] != snapshot["policy_digest"]
    assert snapshot["policy_snapshot"]["priority"] != 999
    unsafe = replace(routed.route, reason="private case narrative and secret", provider=replace(routed.route.provider, base_url="https://secret.invalid/token"))
    safe = route_provenance(unsafe)
    assert safe["reason_code"] == "selection_reason_unavailable"
    assert "private case" not in str(safe)
    assert "secret.invalid" not in str(safe)


@pytest.mark.parametrize("response,expected,revision", [
    (SimpleNamespace(model="gpt-test-2026-01-01"), "gpt-test-2026-01-01", None),
    ({"model": "local:model", "model_version": "v3"}, "local:model", "v3"),
    ({"model": "private narrative is not an identifier", "model_version": "token="}, None, None),
])
def test_provider_metadata_is_separate_from_deployment_and_no_version_is_invented(response, expected, revision):
    events = []
    with correlation_scope(correlation_id="synthetic", request_id="turn-2", debug_sink=lambda *event: events.append(event)):
        result = execute_correlated_model_call(provider="synthetic", model="deployment-alias", agent_name="test", request_payload=[], invoke=lambda: response, route_snapshot={"policy_digest": "pinned"})
    assert result is response
    assert events[0][4]["route_provenance"] == {"policy_digest": "pinned"}
    completed = events[-1][4]
    assert completed["model"] == "deployment-alias"
    assert completed["provider_reported_model"] == expected
    assert completed["provider_reported_model_version"] == revision
    assert completed["model_version_status"] == ("reported" if revision else "unavailable")
    assert events[0][0].parent_request_id == "turn-2"


def test_failed_attempt_is_not_reported_as_completed():
    events = []
    def fail():
        raise TimeoutError("synthetic")
    with correlation_scope(correlation_id="synthetic", request_id="turn-3", debug_sink=lambda *event: events.append(event)):
        with pytest.raises(TimeoutError):
            execute_correlated_model_call(provider="synthetic", model="alias", agent_name="test", request_payload=[], invoke=fail)
    assert [event[3] for event in events] == ["started", "failed"]
