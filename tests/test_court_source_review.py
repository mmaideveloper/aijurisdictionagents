from hashlib import sha256
import json

import httpx
import pytest

from services.court_decision_collector.infosud_source import InfoSudSourceClient
from services.court_decision_collector.source_review import INFOSUD_BASE, inspect_reference


def test_listing_uses_canonical_guid_not_unrelated_id(monkeypatch):
    client = InfoSudSourceClient(base_url=INFOSUD_BASE)
    monkeypatch.setattr(client, "_get_json", lambda **_: {
        "rozhodnutieList": [{"id": "wrong-entity", "uuid": "wrong-uuid", "guid": "canonical"}],
    })
    assert client.list_decisions()[0].guid == "canonical"


@pytest.mark.parametrize("item", [{"id": "wrong"}, {"uuid": "wrong"}, {"guid": ""},
                                  {"guid": 123}, {"guid": " padded "}, {"guid": "control\n"}])
def test_listing_contract_change_aborts_instead_of_enqueuing_wrong_id(monkeypatch, item):
    client = InfoSudSourceClient(base_url=INFOSUD_BASE)
    monkeypatch.setattr(client, "_get_json", lambda **_: {"rozhodnutieList": [item]})
    with pytest.raises(ValueError, match="canonical guid"):
        client.list_decisions()


def test_detail_identifier_is_encoded_as_one_path_segment(monkeypatch):
    client = InfoSudSourceClient(base_url=INFOSUD_BASE)
    guid = "synthetic:left/right?query#fragment"
    paths = []

    def get_json(**kwargs):
        paths.append(kwargs["path"])
        return {"guid": guid}

    monkeypatch.setattr(client, "_get_json", get_json)
    record = client.get_decision(guid)
    assert paths == ["/rozhodnutie/synthetic:left%2Fright%3Fquery%23fragment"]
    assert record.source_guid == guid
    assert record.source_url == INFOSUD_BASE + paths[0]


@pytest.mark.parametrize("payload", [{"guid": "different"}, {}, {"id": "requested"}])
def test_detail_identity_mismatch_cannot_create_a_false_record(monkeypatch, payload):
    client = InfoSudSourceClient(base_url=INFOSUD_BASE)
    monkeypatch.setattr(client, "_get_json", lambda **_: payload)
    with pytest.raises(ValueError, match="does not match"):
        client.get_decision("requested")


@pytest.mark.parametrize("status", [404, 410])
def test_missing_and_absent_from_one_page_never_proves_removal(status):
    paths = []

    def handle(request):
        paths.append(request.url.path)
        if request.url.path.endswith("/missing"):
            return httpx.Response(status)
        if request.url.path.endswith("/control"):
            return httpx.Response(200, json={"guid": "control"})
        return httpx.Response(200, json={"rozhodnutieList": [{"guid": "control"}]})

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        result = inspect_reference(client, source_guid="missing", page=0, size=25)
    assert len(paths) == result["requests"] == 3
    assert result["classification"] == "unresolved_missing"
    assert result["listed_on_sampled_page"] is False
    assert result["control_identity_verified"] is True
    assert result["permanent_unavailability_confirmed"] is False
    assert "missing" not in result["reference_hash"]
    assert result["reference_hash"] == sha256(b"missing").hexdigest()[:16]


def test_alternate_identifier_requires_verified_canonical_detail():
    def handle(request):
        if request.url.path.endswith("/legacy-id"):
            return httpx.Response(404)
        if request.url.path.endswith("/canonical"):
            return httpx.Response(200, json={"guid": "canonical"})
        return httpx.Response(200, json={
            "rozhodnutieList": [{"id": "legacy-id", "guid": "canonical"}],
        })

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        result = inspect_reference(client, source_guid="legacy-id", page=0, size=25)
    assert result["classification"] == "identifier_mismatch_verified"
    assert result["requests"] == 3
    assert "legacy-id" not in json.dumps(result)
    assert "canonical" not in json.dumps(result)


def test_endpoint_wide_404_does_not_quarantine_anything():
    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(404))) as client:
        result = inspect_reference(client, source_guid="synthetic", page=0, size=25)
    assert result["classification"] == "source_endpoint_unavailable"
    assert result["requests"] == 2
    assert result["permanent_unavailability_confirmed"] is False


def test_request_error_reports_type_without_sensitive_message():
    def fail(request):
        raise httpx.ConnectError("private-reference-and-token", request=request)

    with httpx.Client(transport=httpx.MockTransport(fail)) as client:
        result = inspect_reference(client, source_guid="synthetic", page=0, size=25)
    assert result["classification"] == "probe_incomplete"
    assert result["requests"] == 1
    assert "private-reference-and-token" not in json.dumps(result)


def test_collector_transport_logs_never_include_exception_url_or_reference(monkeypatch):
    messages = []

    def fail(*args, **kwargs):
        raise httpx.ConnectTimeout("https://private-url.invalid/sensitive-reference?token=secret")

    monkeypatch.setattr(httpx, "get", fail)
    source = InfoSudSourceClient(base_url=INFOSUD_BASE, retry_attempts=2,
                                retry_backoff_seconds=0, progress_logger=messages.append)
    with pytest.raises(httpx.ConnectTimeout):
        source.get_decision("sensitive-reference")
    assert len(messages) == 2
    assert "sensitive-reference" not in str(messages)
    assert "private-url" not in str(messages)
    assert "secret" not in str(messages)


def test_review_rejects_untrusted_host_without_request():
    requests = []
    with httpx.Client(transport=httpx.MockTransport(requests.append)) as client:
        with pytest.raises(ValueError, match="allowlisted"):
            inspect_reference(client, source_guid="synthetic", page=0, size=25,
                              base_url="https://attacker.invalid")
    assert not requests
