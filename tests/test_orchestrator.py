from pathlib import Path

from aijurisdictionagents.agents import create_judge, create_lawyer
from aijurisdictionagents.llm import MockLLMClient
from aijurisdictionagents.observability import TraceRecorder
from aijurisdictionagents.orchestration import Orchestrator
from aijurisdictionagents.schemas import Document


def test_orchestrator_flow(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()

    documents = [
        Document(
            doc_id="doc-1",
            path=str(tmp_path / "doc.txt"),
            content="Delivery was late according to the agreement.",
        )
    ]

    trace = TraceRecorder(run_dir)
    try:
        llm = MockLLMClient()
        orchestrator = Orchestrator(
            lawyer=create_lawyer(llm),
            judge=create_judge(llm),
            trace=trace,
        )
        result = orchestrator.run(
            "Late delivery dispute",
            documents,
            country="SK",
            language=None,
            question_timeout_seconds=60,
            discussion_type="court",
            user_response_provider=lambda _q, _t: None,
        )
    finally:
        trace.close()

    assert result.final_recommendation
    assert result.judge_rationale
    assert result.citations
    assert len(result.messages) == 4
    assert "could not answer" in result.messages[-1].content.lower()


def test_orchestrator_requires_country(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()

    trace = TraceRecorder(run_dir)
    try:
        llm = MockLLMClient()
        orchestrator = Orchestrator(
            lawyer=create_lawyer(llm),
            judge=create_judge(llm),
            trace=trace,
        )
        try:
            orchestrator.run(
                "Instruction",
                [],
                country="",
                language=None,
                question_timeout_seconds=60,
                user_response_provider=lambda _q, _t: None,
            )
            raise AssertionError("Expected ValueError for missing country.")
        except ValueError:
            pass
    finally:
        trace.close()
    assert (run_dir / "trace.jsonl").exists()


def test_orchestrator_followup_questions(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()

    documents = [
        Document(
            doc_id="doc-1",
            path=str(tmp_path / "doc.txt"),
            content="Delivery was late according to the agreement.",
        )
    ]

    question_answers = iter(["Jurisdiction is SK.", "Second answer."])
    followup_questions = iter(["What if we export to EU?", "finish"])

    def provider(prompt: str, _timeout: float) -> str | None:
        if "other questions" in prompt.lower():
            return next(followup_questions)
        return next(question_answers)

    trace = TraceRecorder(run_dir)
    try:
        llm = MockLLMClient()
        orchestrator = Orchestrator(
            lawyer=create_lawyer(llm),
            judge=create_judge(llm),
            trace=trace,
        )
        result = orchestrator.run(
            "Late delivery dispute",
            documents,
            country="SK",
            language=None,
            question_timeout_seconds=60,
            max_discussion_minutes=0,
            discussion_type="court",
            user_response_provider=provider,
        )
    finally:
        trace.close()

    assert result.messages[-1].content.lower() == "finish"
    assert any("export to eu" in message.content.lower() for message in result.messages)
    assert len(result.messages) == 9


def test_advice_mode_skips_judge_without_request(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()

    documents = [
        Document(
            doc_id="doc-1",
            path=str(tmp_path / "doc.txt"),
            content="Delivery was late according to the agreement.",
        )
    ]

    calls: list[tuple[str, int]] = []

    class RecordingLLM:
        def complete(self, agent_name: str, _prompt: str, _conv, docs) -> str:
            calls.append((agent_name, len(docs)))
            if agent_name == "Lawyer":
                return "LAWYER RESPONSE"
            if agent_name == "Judge":
                return "Decision: APPROVED"
            return "Recommendation: OK\nRationale: OK"

    def provider(prompt: str, _timeout: float) -> str | None:
        if "judge" in prompt.lower():
            return "no"
        return "finish"

    trace = TraceRecorder(run_dir)
    try:
        llm = RecordingLLM()
        orchestrator = Orchestrator(
            lawyer=create_lawyer(llm),
            judge=create_judge(llm),
            trace=trace,
        )
        orchestrator.run(
            "Late delivery dispute",
            documents,
            country="SK",
            language=None,
            discussion_type="advice",
            question_timeout_seconds=60,
            user_response_provider=provider,
        )
    finally:
        trace.close()

    assert ("Lawyer", 1) in calls
    assert all(name != "Judge" for name, _ in calls)


def test_court_mode_retries_on_rejection(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()

    calls: list[str] = []
    state = {"judge_calls": 0}

    class CourtLLM:
        def complete(self, agent_name: str, _prompt: str, _conv, _docs) -> str:
            calls.append(agent_name)
            if agent_name == "Judge":
                state["judge_calls"] += 1
                if state["judge_calls"] == 1:
                    return "Decision: REJECTED"
                return "Decision: APPROVED"
            if agent_name == "Lawyer":
                return f"LAWYER RESPONSE {state['judge_calls']}"
            return "Recommendation: OK\nRationale: OK"

    def provider(prompt: str, _timeout: float) -> str | None:
        if "other questions" in prompt.lower():
            return "finish"
        return None

    trace = TraceRecorder(run_dir)
    try:
        llm = CourtLLM()
        orchestrator = Orchestrator(
            lawyer=create_lawyer(llm),
            judge=create_judge(llm),
            trace=trace,
        )
        orchestrator.run(
            "Late delivery dispute",
            [],
            country="SK",
            language=None,
            discussion_type="court",
            question_timeout_seconds=60,
            max_discussion_minutes=0,
            user_response_provider=provider,
        )
    finally:
        trace.close()

    assert calls.count("Lawyer") >= 2
    assert calls.count("Judge") == 2
