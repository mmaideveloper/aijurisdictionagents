from pathlib import Path

from aijurisdictionagents.cases import CaseStore
from aijurisdictionagents.schemas import Message, OrchestrationResult


def _build_result(messages: list[Message]) -> OrchestrationResult:
    return OrchestrationResult(
        final_recommendation="Recommendation: proceed with a demand letter.",
        judge_rationale="Rationale: gather delivery proof.",
        citations=[],
        messages=messages,
    )


def test_case_store_creates_case_and_copies_files(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "contract.txt").write_text("Contract text", encoding="utf-8")
    (data_dir / "email.eml").write_text("Email text", encoding="utf-8")

    messages = [
        Message(role="user", agent_name="User", content="Initial instruction", sources=[]),
        Message(
            role="assistant",
            agent_name="LawyerSlovakia",
            content="Please upload documents. When was payment made?",
            sources=[],
        ),
        Message(role="user", agent_name="User", content="Payment on 2025-10-12.", sources=[]),
    ]
    result = _build_result(messages)

    store = CaseStore(tmp_path / "cases")
    record = store.create_case(
        instruction="Initial instruction",
        country="SK",
        language="en",
        messages=messages,
        result=result,
        agent_name="LawyerSlovakia",
        data_dir=data_dir,
    )

    assert len(record.case_id) >= 32
    assert (record.path / "case.json").exists()
    assert (record.path / "description.md").exists()
    documents_dir = record.path / "documents"
    assert documents_dir.exists()
    assert len(list(documents_dir.iterdir())) == 2
    assert record.data["documents"]


def test_case_store_appends_discussion(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "contract.txt").write_text("Contract text", encoding="utf-8")

    messages = [
        Message(role="user", agent_name="User", content="Initial instruction", sources=[]),
        Message(
            role="assistant",
            agent_name="LawyerSlovakia",
            content="Please upload documents. When was payment made?",
            sources=[],
        ),
        Message(role="user", agent_name="User", content="Payment on 2025-10-12.", sources=[]),
    ]
    result = _build_result(messages)

    store = CaseStore(tmp_path / "cases")
    record = store.create_case(
        instruction="Initial instruction",
        country="SK",
        language="en",
        messages=messages,
        result=result,
        agent_name="LawyerSlovakia",
        data_dir=data_dir,
    )

    followup_messages = [
        Message(role="user", agent_name="User", content="Follow-up question.", sources=[]),
        Message(
            role="assistant",
            agent_name="LawyerSlovakia",
            content="Do you have delivery confirmation?",
            sources=[],
        ),
    ]
    followup_result = _build_result(followup_messages)

    updated = store.append_discussion(
        case_id=record.case_id,
        messages=followup_messages,
        result=followup_result,
        agent_name="LawyerSlovakia",
        data_dir=None,
    )

    assert len(updated.data["discussions"]) == 2
    assert updated.data["open_questions"] == ["Do you have delivery confirmation?"]
