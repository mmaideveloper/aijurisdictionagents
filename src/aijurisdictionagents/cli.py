from __future__ import annotations

import argparse
import logging
import os
import threading
from pathlib import Path

from dotenv import load_dotenv

from .agents import create_judge, create_lawyer
from .documents import load_documents
from .llm import get_llm_client
from .observability import TraceRecorder, create_run_dir, setup_logging
from .orchestration import Orchestrator


def _mask_secret(value: str) -> str:
    if not value:
        return "unset"
    if len(value) <= 4:
        return "*" * len(value)
    return "*" * (len(value) - 4) + value[-4:]


def _log_token_info(logger: logging.Logger, provider: str) -> None:
    if provider == "openai":
        api_key = os.getenv("OPENAI_API_KEY", "")
        logger.debug("OpenAI API key: %s", _mask_secret(api_key))
    if provider in {"azurefoundry", "azure"}:
        api_key = os.getenv("AZURE_OPENAI_API_KEY", "")
        ad_token = os.getenv("AZURE_OPENAI_AD_TOKEN", "")
        endpoint = os.getenv("AZURE_OPENAI_ENDPOINT", "")
        deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT", "")
        logger.debug("Azure endpoint: %s", endpoint or "unset")
        logger.debug("Azure deployment: %s", deployment or "unset")
        if ad_token:
            logger.debug("Azure AD token: %s", _mask_secret(ad_token))
        else:
            logger.debug("Azure API key: %s", _mask_secret(api_key))


def _timed_input(prompt: str, timeout_seconds: int) -> str | None:
    result: dict[str, str | None] = {"value": None}

    def _reader() -> None:
        try:
            result["value"] = input(prompt)
        except EOFError:
            result["value"] = ""

    thread = threading.Thread(target=_reader, daemon=True)
    thread.start()
    thread.join(timeout_seconds)
    if thread.is_alive():
        return None

    value = (result["value"] or "").strip()
    return value or None


def _prompt_user_with_timeout(question: str) -> str | None:
    print(f"\nAgent question: {question}")
    print("You have 60 seconds to answer. Press Enter to skip.")
    response = _timed_input("Your answer: ", 60)
    if response is None:
        print("No response received within 60 seconds.")
    return response


def main() -> int:
    load_dotenv()
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
    parser.add_argument(
        "--log-level",
        type=str,
        default="DEBUG",
        help="Logging level (DEBUG, INFO, WARNING, ERROR).",
    )
    parser.add_argument(
        "--discussion-max-minutes",
        type=float,
        default=15,
        help="Max discussion time in minutes (0 for unlimited).",
    )
    args = parser.parse_args()

    instruction = args.instruction.strip() or input("Enter your case instructions: ").strip()
    if not instruction:
        print("No instruction provided. Exiting.")
        return 1

    run_dir = create_run_dir(Path("runs"))
    logger = setup_logging(run_dir, log_level=args.log_level)
    logger.info("Run directory: %s", run_dir)

    documents = load_documents(args.data_dir, allow_pdf=args.allow_pdf)
    logger.info("Loaded %d documents", len(documents))

    provider = os.getenv("LLM_PROVIDER", "mock").lower()
    logger.info("LLM provider requested: %s", provider)
    _log_token_info(logger, provider)
    llm = get_llm_client()
    logger.info("LLM provider active: %s (%s)", provider, type(llm).__name__)
    lawyer = create_lawyer(llm)
    judge = create_judge(llm)

    trace = TraceRecorder(run_dir)
    try:
        orchestrator = Orchestrator(lawyer=lawyer, judge=judge, trace=trace, logger=logger)
        result = orchestrator.run(
            instruction,
            documents,
            max_discussion_minutes=args.discussion_max_minutes,
            user_response_provider=_prompt_user_with_timeout,
        )
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
