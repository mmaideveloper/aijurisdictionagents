from __future__ import annotations

import logging
import sys
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Sequence

from app.chat.models import Session

if TYPE_CHECKING:
    from aijurisdictionagents.schemas import Document, OrchestrationResult

REPO_ROOT = Path(__file__).resolve().parents[4]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))


def _load_core_dependencies():
    from aijurisdictionagents.agents import create_judge, create_lawyer_agent
    from aijurisdictionagents.llm import get_llm_client
    from aijurisdictionagents.observability import TraceRecorder
    from aijurisdictionagents.orchestration import Orchestrator

    return create_judge, create_lawyer_agent, get_llm_client, TraceRecorder, Orchestrator


def run_orchestration(
    session: Session,
    instruction: str,
    documents: Sequence[Document],
    question_timeout_seconds: float,
    max_discussion_minutes: float,
    user_response_provider,
    message_callback,
) -> OrchestrationResult:
    create_judge, create_lawyer_agent, get_llm_client, trace_recorder, orchestrator_class = (
        _load_core_dependencies()
    )
    llm = get_llm_client()
    lawyer = create_lawyer_agent(llm, session.country)
    judge = create_judge(llm) if session.discussion_type == "court" else None

    logger = logging.getLogger("aijuristiction-api.core")
    with tempfile.TemporaryDirectory(prefix="aijuris_api_run_") as temp_dir:
        trace = trace_recorder(Path(temp_dir))
        try:
            orchestrator = orchestrator_class(lawyer=lawyer, judge=judge, trace=trace, logger=logger)
            return orchestrator.run(
                instruction,
                documents,
                country=session.country,
                language=session.language,
                question_timeout_seconds=question_timeout_seconds,
                max_discussion_minutes=max_discussion_minutes,
                discussion_type=session.discussion_type,
                user_response_provider=user_response_provider,
                message_callback=message_callback,
            )
        finally:
            trace.close()


def core_message_role(role: str) -> str:
    role_lower = role.lower().strip()
    if role_lower in {"user", "assistant", "system"}:
        return role_lower
    return "assistant"
