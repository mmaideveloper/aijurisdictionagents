from __future__ import annotations

import argparse
from pathlib import Path

from .agents import create_judge, create_lawyer
from .documents import load_documents
from .llm import get_llm_client
from .observability import TraceRecorder, create_run_dir, setup_logging
from .orchestration import Orchestrator


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the legal discussion demo.")
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path("data"),
        help="Folder containing documents to ingest.",
    )
    parser.add_argument(
        "--instruction",
        type=str,
        default="",
        help="User instruction to feed the agents.",
    )
    parser.add_argument(
        "--allow-pdf",
        action="store_true",
        help="Enable PDF ingestion (requires pypdf).",
    )
    args = parser.parse_args()

    instruction = args.instruction.strip() or input("Enter your case instructions: ").strip()
    if not instruction:
        print("No instruction provided. Exiting.")
        return 1

    run_dir = create_run_dir(Path("runs"))
    logger = setup_logging(run_dir)
    logger.info("Run directory: %s", run_dir)

    documents = load_documents(args.data_dir, allow_pdf=args.allow_pdf)
    logger.info("Loaded %d documents", len(documents))

    llm = get_llm_client()
    lawyer = create_lawyer(llm)
    judge = create_judge(llm)

    trace = TraceRecorder(run_dir)
    try:
        orchestrator = Orchestrator(lawyer=lawyer, judge=judge, trace=trace, logger=logger)
        result = orchestrator.run(instruction, documents)
    finally:
        trace.close()

    print("\nFinal Recommendation:\n" + result.final_recommendation)
    print("\nKey Citations:")
    if result.citations:
        for source in result.citations:
            print(f"- {source.filename}: {source.snippet}")
    else:
        print("- None")

    print("\nJudge Rationale:\n" + result.judge_rationale)
    print(f"\nTrace saved to: {run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
