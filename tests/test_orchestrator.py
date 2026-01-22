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
        result = orchestrator.run("Late delivery dispute", documents)
    finally:
        trace.close()

    assert result.final_recommendation
    assert result.judge_rationale
    assert result.citations
    assert len(result.messages) == 3
    assert (run_dir / "trace.jsonl").exists()
