from services.court_decision_collector.fixtures import sample_court_decision_records


def main() -> None:
    record = sample_court_decision_records()[0]
    print("court_decision_collector_demo => ready")
    print(f"source_guid => {record.source_guid}")
    print(f"court => {record.court_name}")
    print(f"public_text_contains_person => {'Jan Novak' in record.public_text}")


if __name__ == "__main__":
    main()
