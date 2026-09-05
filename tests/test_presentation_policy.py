from __future__ import annotations

import pytest

from aijurisdictionagents.orchestration.presentation import (
    PresentationPolicyError,
    build_presentation_block,
    presentation_result_shape,
    select_presentation_renderer,
    validate_presentation_policy,
)


def _policy() -> dict[str, object]:
    return {
        "schema_version": 1,
        "policy_id": "test.presentation.v1",
        "default_renderer": "result_card",
        "renderers": [
            {"renderer_id": "result_card", "version": 1},
            {"renderer_id": "data_table", "version": 1},
            {"renderer_id": "document_preview", "version": 1},
            {"renderer_id": "sanitized_json", "version": 1},
            {"renderer_id": "text", "version": 1},
        ],
        "user_overrides": ["data_table", "sanitized_json", "text"],
        "max_items": 10,
        "max_string_length": 200,
        "max_payload_bytes": 8_000,
    }


def test_explicit_user_json_overrides_model_proposal_and_redacts_sensitive_keys() -> None:
    policy = validate_presentation_policy(_policy(), strict=True)
    assert policy is not None
    selection = select_presentation_renderer(
        policy,
        request_text="Show the result as raw JSON please",
        result_shape="mapping",
        proposed_renderer="result_card",
    )
    block = build_presentation_block(
        policy=policy,
        selection=selection,
        final_answer="Readable result",
        tool_results=[
            {
                "tool_name": "company_check",
                "status": "verified",
                "api_key": "must-not-leak",
                "consent_event_id": "internal-ledger-id",
            }
        ],
    )

    assert block["renderer_id"] == "sanitized_json"
    assert block["selection"]["reason_code"] == "explicit_user_format"
    serialized = str(block)
    assert "must-not-leak" not in serialized
    assert "internal-ledger-id" not in serialized


def test_model_can_select_only_assigned_shape_compatible_renderer() -> None:
    policy = validate_presentation_policy(_policy(), strict=True)
    assert policy is not None

    accepted = select_presentation_renderer(
        policy,
        request_text="Summarize it",
        result_shape="records",
        proposed_renderer="data_table",
    )
    rejected = select_presentation_renderer(
        policy,
        request_text="Summarize it",
        result_shape="records",
        proposed_renderer="action_link",
    )

    assert accepted.renderer.renderer_id == "data_table"
    assert accepted.model_proposal_accepted is True
    assert rejected.renderer.renderer_id == "result_card"
    assert rejected.reason_code == "invalid_model_proposal_flow_default"


def test_incompatible_explicit_format_fails_to_readable_text() -> None:
    policy = validate_presentation_policy(_policy(), strict=True)
    assert policy is not None
    selection = select_presentation_renderer(
        policy,
        request_text="Show this as a table",
        result_shape="document",
    )
    assert selection.renderer.renderer_id == "text"
    assert selection.reason_code == "explicit_format_safe_fallback"


def test_policy_requires_registered_text_fallback() -> None:
    raw = _policy()
    raw["renderers"] = [{"renderer_id": "result_card", "version": 1}]
    raw["user_overrides"] = []
    with pytest.raises(PresentationPolicyError, match="presentation_text_fallback_required"):
        validate_presentation_policy(raw, strict=True)


def test_result_shape_prefers_document_then_records_then_notice() -> None:
    assert presentation_result_shape(
        final_answer="draft",
        tool_results=[],
        artifacts=[{"artifact_type": "legal_document_draft"}],
        status="completed",
    ) == "document"
    assert presentation_result_shape(
        final_answer="results", tool_results=[{"a": 1}, {"a": 2}], artifacts=[], status="completed"
    ) == "records"
    assert presentation_result_shape(
        final_answer="review", tool_results=[], artifacts=[], status="human_review_required"
    ) == "notice"
