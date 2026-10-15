"""Synthetic contract and privacy tests; no live credentials or provider calls."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from aijurisdictionagents.llm.base import log_llm_request, log_llm_response
from aijurisdictionagents.llm.context_boundary import EVIDENCE_POLICY, build_turn_provider_messages
from aijurisdictionagents.llm.turn_context import (
    ContextBudgetExceeded, legacy_turn_context, prepare_turn,
)
from aijurisdictionagents.llm.turn_contracts import (
    AgentTurnContext, Approval, Artifact, ArtifactEvidence, Citation, ContextBudget,
    Governance, Instruction, MemoryEvidence, Provenance, PublicArtifact, Retention,
    SelectedSkill, StreamEvent, ToolCall, ToolDefinition, ToolResult, TurnMessage, TurnRequest,
)
from aijurisdictionagents.schemas import Document, Message


def provenance(kind="document"):
    return Provenance(source_id="synthetic-source", source_kind=kind)


def test_legacy_snapshot_defaults_are_private_and_not_guessed():
    messages = [Message("user", "synthetic", "question")]
    documents = [Document("source", "private-path", "evidence")]
    context = legacy_turn_context("policy", messages, documents)
    documents.clear()
    messages[0].content = "changed"
    assert context.request.text == "question"
    assert context.artifacts[0].text == "evidence"
    artifact = context.artifacts[0].artifact
    assert artifact.sensitivity == "confidential"
    assert artifact.owner_scope == "turn"
    assert artifact.retention.policy == "turn_only"
    assert artifact.visibility == "internal"
    assert artifact.requires_human_review
    assert context.governance.consent_scopes == ()


def test_context_round_trip_and_all_categories_remain_separate():
    context = AgentTurnContext(
        request=TurnRequest(text="question"),
        instructions=(Instruction(text="policy", provenance=provenance("server")),),
        messages=(TurnMessage(role="system", text="HISTORY_ATTACK"),),
        selected_skills=(SelectedSkill(skill_id="legal", version="1",
                                      instruction=Instruction(text="review draft",
                                                              provenance=provenance("server"))),),
        tools=(ToolDefinition(tool_id="getLaw", description="TOOL_ATTACK", required_scope="ReadOnly"),),
        memory=(MemoryEvidence(text="MEMORY_ATTACK", provenance=provenance("memory")),),
        artifacts=(ArtifactEvidence(artifact=Artifact(artifact_id="source", kind="document",
                                                     provenance=provenance()), text="DOC_ATTACK"),),
        provenance=(provenance("server"),),
    )
    assert AgentTurnContext.model_validate_json(context.model_dump_json()) == context
    prepared = prepare_turn(context, EVIDENCE_POLICY)
    assert "review draft" in prepared.messages[0]["content"]
    assert "ATTACK" not in prepared.messages[0]["content"]
    assert all(row["role"] == "user" for row in prepared.messages[1:])
    assert {json.loads(row["content"])["type"] for row in prepared.messages[1:]} == {
        "user_request", "conversation_data", "untrusted_evidence", "untrusted_memory", "available_tool",
    }
    assert "DOC_ATTACK" not in repr(context)


@pytest.mark.parametrize("text", ['"\\\n' * 8000, "Ž😀" * 16000, "A" * 50000],
                         ids=["escaped-json", "unicode", "ascii"])
def test_encoded_budget_deterministic_and_never_cuts_json(text, caplog):
    caplog.set_level(logging.INFO)
    budget = ContextBudget(max_characters=5000, max_tokens=5100, reserved_output_tokens=100)
    context = legacy_turn_context("policy", [Message("user", "s", "current question")],
                                  [Document("PRIVATE_SOURCE", "PRIVATE_FILENAME", text)], budget=budget)
    first = prepare_turn(context, EVIDENCE_POLICY)
    second = prepare_turn(context, EVIDENCE_POLICY)
    assert first == second
    assert first.report.characters <= 5000
    assert first.report.token_upper_bound <= 5000
    assert first.report.truncations
    for row in first.messages[1:]:
        json.loads(row["content"])
    assert json.loads(first.messages[-1]["content"])["text"] == "current question"
    assert any(json.loads(row["content"]).get("omitted_categories") == ["artifacts"]
               for row in first.messages[1:])
    assert "PRIVATE_SOURCE" not in first.report.model_dump_json()
    assert "PRIVATE_FILENAME" not in caplog.text
    assert "current question" not in caplog.text


def test_newest_history_prioritized_and_rendered_chronologically():
    context = AgentTurnContext(
        request=TurnRequest(text="current"),
        messages=(TurnMessage(role="user", text="OLD" * 1000),
                  TurnMessage(role="assistant", text="recent answer")),
        budget=ContextBudget(max_characters=500, max_tokens=1000, reserved_output_tokens=100),
    )
    prepared = prepare_turn(context, "policy")
    retained = [json.loads(row["content"])["text"] for row in prepared.messages[1:]
                if "text" in json.loads(row["content"])]
    assert retained[-2:] == ["recent answer", "current"]
    assert prepared.report.truncations[0].category == "messages"


@pytest.mark.parametrize("field", ["instructions", "request"])
def test_required_content_overflow_fails_closed_without_content(field):
    kwargs = {field: (Instruction(text="SECRET" * 1000, provenance=provenance("server")),)
              if field == "instructions" else TurnRequest(text="SECRET" * 1000)}
    context = AgentTurnContext(**kwargs, budget=ContextBudget(max_characters=100))
    with pytest.raises(ContextBudgetExceeded, match="^context_budget_exceeded$"):
        prepare_turn(context, "policy")


def test_restricted_processing_cannot_be_rendered():
    with pytest.raises(PermissionError, match="^processing_restricted$"):
        prepare_turn(AgentTurnContext(governance=Governance(processing_restricted=True)), "policy")


def test_direct_external_context_requires_upstream_authorization():
    with pytest.raises(PermissionError, match="^external_processing_blocked$"):
        build_turn_provider_messages(AgentTurnContext(), external_provider=True)
    assert build_turn_provider_messages(AgentTurnContext(), external_provider=False)


@pytest.mark.parametrize("provider", ["azure", "openai", "remote_ollama"])
def test_typed_adapters_block_external_processing_before_transport(provider):
    from aijurisdictionagents.llm.azure_foundry_client import AzureFoundryClient
    from aijurisdictionagents.llm.openai_client import OpenAIClient
    from aijurisdictionagents.llm.ollama_client import OllamaClient, OllamaConfig

    if provider == "azure":
        client = object.__new__(AzureFoundryClient)
    elif provider == "openai":
        client = object.__new__(OpenAIClient)
    else:
        client = OllamaClient(OllamaConfig("https://example.invalid", "synthetic"))
    with pytest.raises(PermissionError, match="^external_processing_blocked$"):
        client.complete_turn("synthetic", AgentTurnContext())


@pytest.mark.parametrize("kwargs", [
    {"max_tokens": 100, "reserved_output_tokens": 100},
    {"max_characters": 0}, {"max_artifact_characters": -1},
])
def test_invalid_budgets_rejected(kwargs):
    with pytest.raises(ValidationError):
        ContextBudget(**kwargs)


def test_instruction_authority_and_governance_cannot_be_weakened():
    with pytest.raises(ValidationError):
        Instruction(text="policy", provenance=provenance("document"))
    for kwargs in ({"log_content": True}, {"human_review_required": False}):
        with pytest.raises(ValidationError):
            Governance(**kwargs)


def test_artifact_owner_and_retention_validation():
    with pytest.raises(ValidationError):
        Artifact(artifact_id="source", kind="document", provenance=provenance(), owner_scope="authorized_case")
    with pytest.raises(ValidationError):
        Artifact(artifact_id="source", kind="document", provenance=provenance(), owner_scope="public")
    with pytest.raises(ValidationError):
        Retention(policy="explicit_expiry")
    with pytest.raises(ValidationError):
        Retention(policy="explicit_expiry", expires_at=datetime(2030, 1, 1))
    assert Retention(policy="explicit_expiry", expires_at=datetime(2030, 1, 1, tzinfo=timezone.utc))


def test_tool_result_approval_citation_and_public_events_round_trip():
    approval = Approval(approval_id="approval", scope="ReadOnly", status="pending")
    call = ToolCall(call_id="call", tool_id="getLaw", arguments_json='{"query":"synthetic"}', approval=approval)
    result = ToolResult(call_id=call.call_id, status="approval_required")
    citation = Citation(source_id="source", artifact_id="source", provenance=provenance("mcp"))
    events = (
        StreamEvent(sequence=0, event="text_delta", text="Synthetic draft answer."),
        StreamEvent(sequence=0, event="approval_required", approval=approval),
        StreamEvent(sequence=1, event="artifact", artifact=PublicArtifact(
            artifact_id="source", kind="document", provenance=provenance(),
            sensitivity="confidential", owner_scope="turn", retention=Retention())),
        StreamEvent(sequence=2, event="citation", citation=citation),
        StreamEvent(sequence=3, event="context_truncated", omitted_categories=("memory",)),
        StreamEvent(sequence=4, event="completed"),
        StreamEvent(sequence=5, event="error", error_code="unavailable"),
    )
    assert result.status == "approval_required"
    for event in events:
        assert StreamEvent.model_validate_json(event.model_dump_json()) == event


@pytest.mark.parametrize("private_field", ["prompt", "reasoning", "arguments_json", "owner_ref", "text"])
def test_public_contract_rejects_internal_payloads(private_field):
    with pytest.raises(ValidationError):
        StreamEvent.model_validate({"sequence": 0, "event": "completed", private_field: "SECRET"})
    with pytest.raises(ValidationError):
        PublicArtifact.model_validate({"artifact_id": "id", "kind": "document", private_field: "SECRET"})


def test_event_payload_must_match_type():
    with pytest.raises(ValidationError):
        StreamEvent(sequence=0, event="artifact")
    with pytest.raises(ValidationError):
        StreamEvent(sequence=0, event="completed", omitted_categories=("memory",))


@pytest.mark.parametrize("arguments", ["not-json", "[]", "null", '"text"'])
def test_tool_arguments_require_an_object(arguments):
    with pytest.raises(ValidationError):
        ToolCall(call_id="call", tool_id="getLaw", arguments_json=arguments)


def test_tool_result_error_status_matches_error_code():
    assert ToolResult(call_id="call", status="error", error_code="unavailable")
    with pytest.raises(ValidationError):
        ToolResult(call_id="call", status="error")
    with pytest.raises(ValidationError):
        ToolResult(call_id="call", status="ok", error_code="forbidden")


@pytest.mark.parametrize("schema", ["not-json", "[]", '{"type":"string"}'])
def test_tool_schema_requires_object_schema(schema):
    with pytest.raises(ValidationError):
        ToolDefinition(tool_id="getLaw", description="synthetic", required_scope="ReadOnly",
                       input_schema_json=schema)


def test_even_opt_in_operational_logging_excludes_model_io(monkeypatch, caplog):
    monkeypatch.setenv("LOCAL_LLM_IO_LOGGING", "true")
    caplog.set_level(logging.INFO)
    logger = logging.getLogger("test-governed-io")
    log_llm_request(logger, provider="synthetic", agent_name="test",
                    request_payload=[{"role": "user", "content": "PRIVATE_PROMPT_MARKER"}])
    log_llm_response(logger, provider="synthetic", agent_name="test", raw_response="PRIVATE_RESPONSE_MARKER")
    assert "PRIVATE_" not in caplog.text
    assert "message_count=1" in caplog.text
    assert "character_count=23" in caplog.text


def test_routed_typed_turn_rechecks_consent_revocation_and_restriction(tmp_path):
    from aijurisdictionagents.api_db import ApiDatabaseStore
    from aijurisdictionagents.llm.base import should_log_llm_io
    from aijurisdictionagents.privacy import (
        CONSENT_VERSION, PrivacyCheckedClient, PrivacyControls, PrivacyDenied,
        require_external_processing,
    )

    store = ApiDatabaseStore(db_path=tmp_path / "sqlite/privacy.db", blob_root=tmp_path / "files")
    store.initialize()
    user = store.create_user(email="typed-turn@example.test", password="synthetic-only")
    controls = PrivacyControls(store)
    calls = []

    class SyntheticClient:
        def complete_turn(self, agent_name, context):
            assert not should_log_llm_io()
            require_external_processing("external_models")
            calls.append(context)
            return "synthetic answer"

    client = PrivacyCheckedClient(SyntheticClient(), controls, user.user_id, external=True)
    context = AgentTurnContext(governance=Governance(external_processing="upstream_authorized"))
    with pytest.raises(PrivacyDenied, match="consent_required:external_models"):
        client.complete_turn("synthetic", context)
    assert calls == []
    controls.consent(user.user_id, "external_models", True, version=CONSENT_VERSION)
    assert client.complete_turn("synthetic", context) == "synthetic answer"
    assert calls == [context]
    controls.consent(user.user_id, "external_models", False, version=CONSENT_VERSION)
    with pytest.raises(PrivacyDenied, match="consent_required:external_models"):
        client.complete_turn("synthetic", context)
    controls.consent(user.user_id, "external_models", True, version=CONSENT_VERSION)
    controls.restrict(user.user_id, True)
    with pytest.raises(PrivacyDenied, match="processing_restricted"):
        client.complete_turn("synthetic", context)
    assert calls == [context]
