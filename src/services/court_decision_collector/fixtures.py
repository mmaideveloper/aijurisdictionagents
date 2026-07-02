from __future__ import annotations

from .domain import CourtDecisionRecord
from .infosud_source import InfoSudDecisionRef
from .pseudonymization import pseudonymize_court_decision_text


def sample_court_decision_records() -> list[CourtDecisionRecord]:
    raw_text = (
        "Okresny sud Bratislava I rozhodol v spore zalobcu Jan Novak proti zalovanej "
        "Eva Kovacova o zaplatenie dlznej sumy. S?d posudzoval najomnu zmluvu, "
        "ome?kanie platby a urok z ome?kania."
    )
    return [
        CourtDecisionRecord(
            source_system="infosud",
            source_guid="fixture-sk-decision-1",
            court_name="Okresny sud Bratislava I",
            court_type="Okresny sud",
            decision_form="rozsudok",
            nature="civilne",
            file_number="12C/34/2024",
            case_number="1234567890",
            ecli="ECLI:SK:OSBA1:2024:1234567890.1",
            issue_date="2024-04-10",
            indexed_at="2024-04-11",
            update_date="2024-04-11",
            source_url="https://obcan.justice.sk/pilot/isu/sudy/rozhodnutia",
            raw_text=raw_text,
            pseudonymized_text=pseudonymize_court_decision_text(raw_text),
            metadata={"fixture": True, "legal_area": "civil"},
        )
    ]


def sample_court_decision_loop_records() -> list[CourtDecisionRecord]:
    records = sample_court_decision_records()
    for index, year in enumerate((2023, 2022), start=2):
        raw_text = (
            f"Krajsky sud Bratislava rozhodoval vo veci spisovej znacky {index}Co/10/{year}. "
            "Rozhodnutie sa tyka zmluvnej povinnosti, omeškania a dokazovania."
        )
        records.append(
            CourtDecisionRecord(
                source_system="infosud",
                source_guid=f"fixture-sk-decision-{index}",
                court_name="Krajsky sud Bratislava",
                court_type="Krajsky sud",
                decision_form="uznesenie",
                nature="civilne",
                file_number=f"{index}Co/10/{year}",
                case_number=f"123456789{index}",
                ecli=f"ECLI:SK:KSBA:{year}:123456789{index}.1",
                issue_date=f"{year}-03-0{index}",
                indexed_at=f"{year}-03-1{index}",
                update_date=f"{year}-03-1{index}",
                source_url="https://obcan.justice.sk/pilot/isu/sudy/rozhodnutia",
                raw_text=raw_text,
                pseudonymized_text=pseudonymize_court_decision_text(raw_text),
                metadata={"fixture": True, "legal_area": "civil", "ordinal": index},
            )
        )
    return records


class FixtureCourtDecisionSource:
    source_system = "infosud"

    def __init__(self, records: list[CourtDecisionRecord] | None = None) -> None:
        self.records = sample_court_decision_loop_records() if records is None else records
        self._by_guid = {record.source_guid: record for record in self.records}

    def list_decisions(self, *, page: int = 0, size: int = 25) -> list[InfoSudDecisionRef]:
        start = page * size
        end = start + size
        return [
            InfoSudDecisionRef(
                guid=record.source_guid,
                label=record.ecli or record.file_number or record.source_guid,
            )
            for record in self.records[start:end]
        ]

    def get_decision(self, guid: str) -> CourtDecisionRecord:
        return self._by_guid[guid]
