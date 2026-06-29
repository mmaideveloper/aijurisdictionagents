from __future__ import annotations

from .domain import CourtDecisionRecord
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
