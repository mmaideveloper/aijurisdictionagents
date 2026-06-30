from services.court_decision_collector.fixtures import FixtureCourtDecisionSource, sample_court_decision_records
from services.court_decision_collector.infosud_source import record_from_infosud_payload
from services.court_decision_collector.postgres_store import CourtDecisionCollectorStatus
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
