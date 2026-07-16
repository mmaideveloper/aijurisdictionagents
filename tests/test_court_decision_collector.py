from hashlib import sha256

import httpx

from services.court_decision_collector.config import CourtDecisionCollectorConfig
from services.court_decision_collector.fixtures import FixtureCourtDecisionSource, sample_court_decision_records
from services.court_decision_collector.infosud_source import InfoSudSourceClient, record_from_infosud_payload
from services.court_decision_collector.postgres_store import (
    CourtDecisionCollectorStatus,
    _parse_issue_date,
    normalize_court_name,
)
from services.court_decision_collector.pseudonymization import pseudonymize_court_decision_text
from services.court_decision_collector.service import CourtDecisionCollectorService


class FakeStore:
    def __init__(self) -> None:
        self.saved = []
        self.import_states = {}

    def upsert_decision(self, record):
        self.saved.append(record)
        return type("Stored", (), {"decision_id": "decision-1", "version_id": "version-1", "state": "created"})()

    def save_import_state(
        self,
        *,
        source_system: str,
        cursor_kind: str,
        last_source_guid: str,
        status: str,
        conn=None,
    ) -> None:
        self.import_states[(source_system, cursor_kind)] = CourtDecisionCollectorStatus(
            last_processed_at="2026-06-30T00:00:00+00:00",
            last_source_guid=last_source_guid,
            status=status,
        )

    def get_import_state(self, *, source_system: str, cursor_kind: str) -> CourtDecisionCollectorStatus:
        return self.import_states.get(
            (source_system, cursor_kind),
            CourtDecisionCollectorStatus(last_processed_at="", last_source_guid="", status="not_started"),
        )


def test_issue_date_parser_supports_source_and_iso_dates_without_fabrication() -> None:
    assert str(_parse_issue_date("31.12.2012")) == "2012-12-31"
    assert str(_parse_issue_date("2026-06-29")) == "2026-06-29"
    assert _parse_issue_date("31.02.2012") is None
    assert _parse_issue_date("") is None


def test_court_name_normalization_is_diacritic_insensitive_and_exact() -> None:
    assert normalize_court_name("Okresny sud Poprad") == "okresny sud poprad"
    assert normalize_court_name("Okresný súd Poprad") == "okresny sud poprad"
    assert normalize_court_name("Okresný súd Kežmarok") != "okresny sud poprad"

class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self):
        return self.payload


def test_config_reads_infosud_timeout_retry_settings(monkeypatch) -> None:
    monkeypatch.setenv("COURT_DECISIONS_DB_CLOUD", "postgresql://postgres:postgres@db/court_decisions_sk")
    monkeypatch.setenv("COURT_DECISIONS_SOURCE_TIMEOUT_SECONDS", "120")
    monkeypatch.setenv("COURT_DECISIONS_SOURCE_RETRY_ATTEMPTS", "4")
    monkeypatch.setenv("COURT_DECISIONS_SOURCE_RETRY_BACKOFF_SECONDS", "1.5")

    config = CourtDecisionCollectorConfig.from_env()

    assert config.source_timeout_seconds == 120
    assert config.source_retry_attempts == 4
    assert config.source_retry_backoff_seconds == 1.5
    config.validate()


def test_infosud_list_decisions_retries_connect_timeout_with_safe_context(monkeypatch) -> None:
    messages = []
    sleeps = []
    calls = []

    def fake_get(url, **kwargs):
        calls.append((url, kwargs))
        if len(calls) == 1:
            raise httpx.ConnectTimeout("timed out")
        return FakeResponse(
            {
                "rozhodnutieList": [
                    {"guid": "decision-guid-1", "spisovaZnacka": "12C/34/2026"},
                ],
            }
        )

    monkeypatch.setattr(httpx, "get", fake_get)
    client = InfoSudSourceClient(
        base_url="https://obcan.justice.sk/pilot/api/ress-isu-service/v1",
        timeout_seconds=90,
        retry_attempts=2,
        retry_backoff_seconds=0.25,
        progress_logger=messages.append,
        sleep_fn=sleeps.append,
    )

    refs = client.list_decisions(page=5362, size=25)

    assert [ref.guid for ref in refs] == ["decision-guid-1"]
    assert len(calls) == 2
    assert calls[0][1]["params"] == {"page": 5362, "size": 25}
    assert calls[0][1]["timeout"] == 90
    assert sleeps == [0.25]
    assert any(
        (
            "infosud_source_request_retry stage=list_decisions page=5362 size=25 "
            "attempt=1 max_attempts=2 timeout_seconds=90 error_type=ConnectTimeout"
        )
        in message
        for message in messages
    )


def test_infosud_detail_failure_logs_hashed_guid_without_raw_identifier(monkeypatch) -> None:
    messages = []
    guid = "raw-guid-value"
    expected_hash = sha256(guid.encode("utf-8")).hexdigest()[:12]

    def fake_get(url, **kwargs):
        raise httpx.ReadTimeout("The read operation timed out")

    monkeypatch.setattr(httpx, "get", fake_get)
    client = InfoSudSourceClient(
        base_url="https://obcan.justice.sk/pilot/api/ress-isu-service/v1",
        timeout_seconds=45,
        retry_attempts=1,
        retry_backoff_seconds=0,
        progress_logger=messages.append,
    )

    try:
        client.get_decision(guid)
    except httpx.ReadTimeout:
        pass

    assert any(
        (
            "infosud_source_request_failed stage=get_decision "
            f"guid_hash={expected_hash} attempt=1 max_attempts=1"
        )
        in message
        for message in messages
    )
    assert not any(guid in message for message in messages)


def test_pseudonymization_removes_common_person_names() -> None:
    text = "Jan Novak byva na ulici Hlavna 12 a narodil sa 01.01.1980."

    sanitized = pseudonymize_court_decision_text(text)

    assert "Jan Novak" not in sanitized
    assert "01.01.1980" not in sanitized


def test_infosud_payload_maps_to_record_with_public_text() -> None:
    payload = {
        "guid": "abc",
        "sud": {"nazov": "Okresny sud Zilina", "typSudu": "Okresny sud"},
        "spisovaZnacka": "1C/2/2024",
        "ecli": "ECLI:SK:OSZA:2024:1",
        "text": "Sud rozhodol vo veci Jan Novak proti Eva Kovacova.",
    }

    record = record_from_infosud_payload(
        payload,
        source_base_url="https://obcan.justice.sk/pilot/api/ress-isu-service/v1",
    )

    assert record.source_guid == "abc"
    assert record.court_name == "Okresny sud Zilina"
    assert "Jan Novak" not in record.public_text


def test_infosud_payload_prefers_original_issuing_court_after_court_reorganization() -> None:
    payload = {
        "guid": "kezmarok-origin",
        "sud": {"nazov": "Okresný súd Poprad", "registreGuid": "sud_160"},
        "povodnySud": {"nazov": "Okresný súd Kežmarok", "registreGuid": "sud_159"},
        "ecli": "ECLI:SK:OSKK:2013:8413010378.1",
        "datumVydania": "14.11.2013",
    }

    record = record_from_infosud_payload(
        payload,
        source_base_url="https://obcan.justice.sk/pilot/api/ress-isu-service/v1",
    )

    assert record.court_name == "Okresný súd Kežmarok"


def test_service_logs_current_processing_decision() -> None:
    messages = []
    store = FakeStore()
    service = CourtDecisionCollectorService(store=store, progress_logger=messages.append)

    summary = service.sync_records(sample_court_decision_records())

    assert summary.processed == 1
    assert store.saved[0].source_guid == "fixture-sk-decision-1"
    assert any(
        (
            "processing_judicial_decision source_guid=fixture-sk-decision-1 "
            "number=12C/34/2024 year=2024 status=processing"
        )
        in item
        for item in messages
    )
    assert any(
        (
            "processed_judicial_decision source_guid=fixture-sk-decision-1 "
            "number=12C/34/2024 year=2024 status=created"
        )
        in item
        for item in messages
    )


def test_service_loop_stops_mid_run_then_resumes_until_current() -> None:
    messages = []
    store = FakeStore()
    source = FixtureCourtDecisionSource()
    service = CourtDecisionCollectorService(store=store, source=source, progress_logger=messages.append)

    first = service.run_until_current(page_size=1, stop_after_decisions=1)
    state_after_stop = store.get_import_state(source_system="infosud", cursor_kind="live_loop")

    assert first.processed == 1
    assert state_after_stop.last_source_guid == "fixture-sk-decision-1"
    assert state_after_stop.status == "stopped_mid_run"
    assert any("collector_loop_stopped reason=stop_after_decisions status=stopped_mid_run" in item for item in messages)

    second = service.run_until_current(page_size=1)
    final_state = store.get_import_state(source_system="infosud", cursor_kind="live_loop")

    assert second.processed == 2
    assert [record.source_guid for record in store.saved] == [
        "fixture-sk-decision-1",
        "fixture-sk-decision-2",
        "fixture-sk-decision-3",
    ]
    assert final_state.last_source_guid == "fixture-sk-decision-3"
    assert final_state.status == "up_to_date"
    assert any("resume_state source_system=infosud cursor_kind=live_loop" in item for item in messages)
    assert any("collector_loop_stopped reason=no_new_decisions status=up_to_date" in item for item in messages)


def test_worker_loop_waits_after_no_new_decisions() -> None:
    messages = []
    sleeps = []
    store = FakeStore()
    source = FixtureCourtDecisionSource(records=[])
    service = CourtDecisionCollectorService(store=store, source=source, progress_logger=messages.append)

    summary = service.run_worker_loop(
        page_size=1,
        poll_seconds=30,
        max_idle_cycles=1,
        sleep_fn=sleeps.append,
    )

    assert summary.processed == 0
    assert sleeps == []
    assert store.get_import_state(source_system="infosud", cursor_kind="live_loop").status == "up_to_date"
    assert any("waiting_for_new_judicial_decisions status=up_to_date idle_cycles=1 wait_seconds=30" in item for item in messages)
    assert any("collector_worker_stopped reason=max_idle_cycles idle_cycles=1 processed=0" in item for item in messages)
