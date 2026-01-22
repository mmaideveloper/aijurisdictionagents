from __future__ import annotations

from pathlib import Path

from aijurisdictionagents.agents import create_judge, create_lawyer
from aijurisdictionagents.documents import load_documents
from aijurisdictionagents.llm import get_llm_client
from aijurisdictionagents.observability import TraceRecorder, create_run_dir, setup_logging
from aijurisdictionagents.orchestration import Orchestrator


def main() -> None:
    instruction = (
        "We believe the contract was breached due to late delivery. "
        "Assess the strongest arguments and likely outcome."
    )

    run_dir = create_run_dir(Path("runs"))
    logger = setup_logging(run_dir)

    documents = load_documents(Path("data"))
    llm = get_llm_client()
    lawyer = create_lawyer(llm)
    judge = create_judge(llm)

    trace = TraceRecorder(run_dir)
    try:
        orchestrator = Orchestrator(lawyer=lawyer, judge=judge, trace=trace, logger=logger)
        result = orchestrator.run(instruction, documents)
    finally:
        trace.close()

    print("Final Recommendation:")
    print(result.final_recommendation)
    print("\nCitations:")
    for source in result.citations:
        print(f"- {source.filename}: {source.snippet}")
    print("\nJudge Rationale:")
    print(result.judge_rationale)


if __name__ == "__main__":
    main()
