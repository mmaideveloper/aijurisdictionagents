from services.court_decision_collector.fixtures import sample_court_decision_records
from services.court_decision_collector.infosud_source import record_from_infosud_payload
from services.court_decision_collector.pseudonymization import pseudonymize_court_decision_text
from services.court_decision_collector.service import CourtDecisionCollectorService


class FakeStore:
    def __init__(self) -> None:
        self.saved = []

    def upsert_decision(self, record):
        self.saved.append(record)
        return type("Stored", (), {"decision_id": "decision-1", "version_id": "version-1", "state": "created"})()


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
