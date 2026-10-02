from types import SimpleNamespace
import pytest
from fastapi import HTTPException
from app.cases_api import get_citation_full_law
from app.chat import mcp_law_context
from app.chat.api import _legal_source_citation_inputs, _legal_source_citations_from_processing_events


def store(*, authenticated=True, owner="user"):
    citation = SimpleNamespace(citation_id="citation", source_id="source", source_type="law",
                               effective_from="2025-07-01", title="Public law", law_number="190/2003")
    return SimpleNamespace(
        authenticate_user_device_auth_token=lambda **_: SimpleNamespace(is_enabled=True) if authenticated else None,
        get_case=lambda **_: SimpleNamespace(user_id=owner, status="open"),
        list_case_citations=lambda **_: [citation],
    )


def test_full_law_requires_authentication_and_case_ownership():
    for data, status in ((store(authenticated=False), 401), (store(owner="someone-else"), 404)):
        with pytest.raises(HTTPException) as raised:
            get_citation_full_law("case", "citation", "user", "device", "token", data)
        assert raised.value.status_code == status


def test_full_law_pages_same_version_and_does_not_return_internal_urls(monkeypatch):
    calls = []
    def call(name, args):
        calls.append(args)
        return {"document_id": "source", "version_id": "v1", "effective_from": "2025-07-01", "content_text": "first" if not args["offset"] else "last",
                "content_truncated": not args["offset"], "next_offset": 5,
                "source_url": "http://internal-mcp/private"}
    monkeypatch.setattr(mcp_law_context, "_call_mcp_tool", call)
    result = get_citation_full_law("case", "citation", "user", "device", "token", store())
    assert result["content"] == "firstlast"
    assert "source_url" not in result
    assert [item["offset"] for item in calls] == [0, 5]
    assert all(item["effective_from"] == "2025-07-01" for item in calls)


def test_full_law_fails_closed_on_version_mismatch(monkeypatch):
    monkeypatch.setattr(mcp_law_context, "_call_mcp_tool", lambda *_: {
        "version_id": "wrong", "effective_from": "2026-01-01", "content_text": "not the cited version"})
    with pytest.raises(HTTPException) as raised:
        get_citation_full_law("case", "citation", "user", "device", "token", store())
    assert raised.value.status_code == 503


def test_same_law_multiple_sections_survive_both_normalization_steps():
    citations = [{"source_type": "law", "source_id": "source", "title": "Law", "section": f"§ {section}",
                  "effective_from": "2025-07-01"} for section in (4, 5, 6, 7)]
    normalized = _legal_source_citations_from_processing_events([{"details": {"citations": citations}}])
    result = _legal_source_citation_inputs(metadata={"legal_source_citations": normalized})
    assert [item["section"] for item in result] == ["§ 4", "§ 5", "§ 6", "§ 7"]


def test_missing_citation_does_not_retrieve_any_source(monkeypatch):
    def unexpected(*_):
        pytest.fail("Missing citation must not trigger source retrieval")
    monkeypatch.setattr(mcp_law_context, "_call_mcp_tool", unexpected)
    with pytest.raises(HTTPException) as raised:
        get_citation_full_law("case", "missing", "user", "device", "token", store())
    assert raised.value.status_code == 404


def test_collector_summary_does_not_duplicate_retrieved_law_version():
    from app.chat.api import _case_citation_inputs_from_result
    result = SimpleNamespace(metadata={
        "legal_source_citations": [{"source_type": "law", "source_id": "retrieved-id", "title": "Law",
                                    "law_number": "190/2003 Z. z.", "section": "§ 4", "effective_from": "2025-07-01"}],
        "law_citations": [{"law_identifier": "190/2003 Z.z.", "effective_from": "2025-07-01", "title": "Law"}],
    })
    citations = _case_citation_inputs_from_result(case_id="case", result=result)
    assert len(citations) == 1
    assert citations[0]["source_id"] == "retrieved-id"


@pytest.mark.parametrize("payload", [
    {"document_id": "another-source", "content_text": "Wrong source"},
    {"document_id": "source", "content_text": "part", "content_truncated": True, "next_offset": 0},
    {"document_id": "source", "content_text": ""},
])
def test_invalid_source_or_pagination_fails_closed(monkeypatch, payload):
    monkeypatch.setattr(mcp_law_context, "_call_mcp_tool", lambda *_: {
        "version_id": "v1", "effective_from": "2025-07-01", **payload})
    with pytest.raises(HTTPException) as raised:
        get_citation_full_law("case", "citation", "user", "device", "token", store())
    assert raised.value.status_code == 503
