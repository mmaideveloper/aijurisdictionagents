import hashlib

from services.court_decision_collector.fixtures import sample_court_decision_records
from services.court_decision_collector.infosud_source import InfoSudSourceClient


def main() -> None:
    record = sample_court_decision_records()[0]
    source_client = InfoSudSourceClient(
        base_url="https://obcan.justice.sk/pilot/api/ress-isu-service/v1",
        timeout_seconds=90,
        retry_attempts=3,
        retry_backoff_seconds=5,
    )
    print("court_decision_collector_demo => ready")
    reference_hash = hashlib.sha256(record.source_guid.encode("utf-8")).hexdigest()[:12]
    print(f"reference_hash => {reference_hash}")
    print("scheduler => new data first, 10000 committed decisions per UTC day")
    print("backfill => runs only when the durable new-data queue is empty")
    print(f"public_text_contains_person => {'Jan Novak' in record.public_text}")
    print(f"infosud_timeout_seconds => {source_client.timeout_seconds:g}")
    print(f"infosud_retry_attempts => {source_client.retry_attempts}")


if __name__ == "__main__":
    main()
