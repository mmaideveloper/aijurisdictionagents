from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

from .agents import create_judge, create_layer_agent
from .cases import CaseStore
from .documents import load_documents
from .jurisdiction import is_slovakia
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


def _timed_input(prompt: str, timeout_seconds: float) -> str | None:
    if os.name == "nt":
        return _timed_input_windows(prompt, timeout_seconds)
    return _timed_input_posix(prompt, timeout_seconds)


def _timed_input_windows(prompt: str, timeout_seconds: float) -> str | None:
    import msvcrt  # pylint: disable=import-outside-toplevel

    sys.stdout.write(prompt)
    sys.stdout.flush()

    buffer: list[str] = []
    start_time = time.monotonic()
    while True:
        if msvcrt.kbhit():
            char = msvcrt.getwch()
            if char in ("\r", "\n"):
                sys.stdout.write("\n")
                sys.stdout.flush()
                break
            if char == "\003":
                raise KeyboardInterrupt
            if char == "\b":
                if buffer:
                    buffer.pop()
                    sys.stdout.write("\b \b")
                    sys.stdout.flush()
                continue
            buffer.append(char)
            sys.stdout.write(char)
            sys.stdout.flush()

        if (time.monotonic() - start_time) >= timeout_seconds:
            return None
        time.sleep(0.05)

    value = "".join(buffer).strip()
    return value or None


def _timed_input_posix(prompt: str, timeout_seconds: float) -> str | None:
    import select  # pylint: disable=import-outside-toplevel

    sys.stdout.write(prompt)
    sys.stdout.flush()

    ready, _, _ = select.select([sys.stdin], [], [], timeout_seconds)
    if not ready:
        return None

    line = sys.stdin.readline()
    value = line.strip()
    return value or None


def _prompt_user_with_timeout(question: str, timeout_seconds: float) -> str | None:
    if timeout_seconds <= 0:
        print("\nNo time remaining for a user response.")
        return None

    print(f"\nLayer Agent question: {question}")
    seconds_display = int(round(timeout_seconds))
    if seconds_display >= 60:
        minutes = seconds_display // 60
        print(
            f"You have {minutes} minutes ({seconds_display} seconds) to answer. "
            "Press Enter to skip."
        )
    else:
        print(f"You have {seconds_display} seconds to answer. Press Enter to skip.")
    response = _timed_input("Your answer: ", timeout_seconds)
    if response is None:
        print("No response received within the allotted time.")
    return response


def main() -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Run the legal discussion demo.")
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=None,
        help="Folder containing documents to ingest (optional).",
    )
    parser.add_argument(
        "--instruction",
        type=str,
        default="",
        help="User instruction to feed the agents.",
    )
    parser.add_argument(
        "--country",
        type=str,
        required=True,
        help="Country/jurisdiction for the case (ISO 3166-1 code recommended).",
    )
    parser.add_argument(
        "--language",
        type=str,
        default="",
        help="Output language for final results (BCP-47 tag recommended).",
    )
    parser.add_argument(
        "--question-timeout-minutes",
        type=float,
        default=5,
        help="Minutes to wait for each user answer (default: 5).",
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
    parser.add_argument(
        "--discussion-type",
        type=str,
        default="advice",
        choices=["advice", "court"],
        help="Type of discussion: advice or court.",
    )
    parser.add_argument(
        "--case-id",
        type=str,
        default="",
        help="Existing case ID to append a new discussion entry (advice + Slovakia only).",
    )
    args = parser.parse_args()

    instruction = args.instruction.strip() or input("Enter your case instructions: ").strip()
    if not instruction:
        print("No instruction provided. Exiting.")
        return 1

    run_dir = create_run_dir(Path("runs"))
    logger = setup_logging(run_dir, log_level=args.log_level)
    logger.info("Run directory: %s", run_dir)

    if args.data_dir is None:
        documents = []
        logger.info("Loaded 0 documents (no data directory provided).")
    else:
        documents = load_documents(args.data_dir, allow_pdf=args.allow_pdf)
        logger.info("Loaded %d documents", len(documents))
    logger.info(
        "Case context: country=%s output_language=%s",
        args.country,
        args.language or "user_input_language",
    )

    provider = os.getenv("LLM_PROVIDER", "mock").lower()
    logger.info("LLM provider requested: %s", provider)
    _log_token_info(logger, provider)
    llm = get_llm_client()
    logger.info("LLM provider active: %s (%s)", provider, type(llm).__name__)
    lawyer = create_layer_agent(llm, args.country)
    judge = create_judge(llm)

    trace = TraceRecorder(run_dir)
    try:
        orchestrator = Orchestrator(lawyer=lawyer, judge=judge, trace=trace, logger=logger)
        result = orchestrator.run(
            instruction,
            documents,
            country=args.country,
            language=args.language or None,
            question_timeout_seconds=args.question_timeout_minutes * 60,
            max_discussion_minutes=args.discussion_max_minutes,
            discussion_type=args.discussion_type,
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

    case_id = (args.case_id or "").strip()
    if args.discussion_type == "advice" and is_slovakia(args.country):
        case_store = CaseStore(Path("cases"))
        try:
            if case_id:
                case_record = case_store.append_discussion(
                    case_id=case_id,
                    messages=result.messages,
                    result=result,
                    agent_name=lawyer.name,
                    data_dir=args.data_dir,
                )
            else:
                case_record = case_store.create_case(
                    instruction=instruction,
                    country=args.country,
                    language=args.language or None,
                    messages=result.messages,
                    result=result,
                    agent_name=lawyer.name,
                    data_dir=args.data_dir,
                )
            print(f"\nCase stored: {case_record.case_id}")
            print(f"Case folder: {case_record.path}")
        except Exception as exc:
            logger.exception("Failed to store case: %s", exc)
    elif case_id:
        logger.warning("Ignoring --case-id because this is not Slovak advice mode.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
