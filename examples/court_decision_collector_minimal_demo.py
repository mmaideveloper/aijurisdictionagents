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
    print(f"source_guid => {record.source_guid}")
    print(f"court => {record.court_name}")
    print(f"public_text_contains_person => {'Jan Novak' in record.public_text}")
    print(f"infosud_timeout_seconds => {source_client.timeout_seconds:g}")
    print(f"infosud_retry_attempts => {source_client.retry_attempts}")


if __name__ == "__main__":
    main()
