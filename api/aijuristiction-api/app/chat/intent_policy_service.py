from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata

from pydantic import BaseModel


def is_legal_research_request(value: str) -> bool:
    normalized = unicodedata.normalize("NFKD", value.casefold())
    canonical = "".join(char for char in normalized if not unicodedata.combining(char))
    canonical = re.sub(r"\s+", " ", canonical).strip()
    if re.search(r"\b(zakon\w*|law|laws)\b", canonical):
        return True
    return any(
        marker in canonical
        for marker in (
            "pravny predpis",
            "pravneho predpis",
            "pravnych predpis",
            "zakon c.",
            "zakona c.",
            "law no.",
            "legal act",
            "statute",
            "sudne rozhodnut",
            "sudnych rozhodnut",
            "rozhodnutia sud",
            "judikat",
            "judikatur",
            "case law",
            "court decision",
        )
    )


class PlannedDocumentTask(BaseModel):
    task_id: str
    description: str


@dataclass(frozen=True)
class DocumentIntentPolicy:
    policy_id: str
    phrases: tuple[str, ...]
    required_document_terms: tuple[str, ...]
    tasks: tuple[PlannedDocumentTask, ...]
    guidance_lines: tuple[str, ...]
    requires_processed_documents: bool = False


@dataclass(frozen=True)
class DocumentPolicyMatch:
    policy: DocumentIntentPolicy
    position: int


@dataclass(frozen=True)
class DocumentPolicyPlan:
    ordered_policies: tuple[DocumentIntentPolicy, ...]
    ordered_tasks: tuple[PlannedDocumentTask, ...]


_DOCUMENT_POLICY_REQUIRED_TERMS = (
    "document",
    "documents",
    "uploaded",
    "upload",
    "contract",
    "agreement",
    "pdf",
    "dokument",
    "dokumenty",
    "dokumente",
    "zmluv",
    "vertrag",
)

_DOCUMENT_INTENT_POLICIES: tuple[DocumentIntentPolicy, ...] = (
    DocumentIntentPolicy(
        policy_id="document_analysis",
        phrases=(
            "analyze",
            "analyse",
            "analysis",
            "review",
            "validate",
            "check",
            "inspect",
            "analyz",
            "skontrol",
            "posud",
            "preskum",
            "kontroll",
            "pruf",
        ),
        required_document_terms=_DOCUMENT_POLICY_REQUIRED_TERMS,
        tasks=(
            PlannedDocumentTask(
                task_id="review_uploaded_document",
                description="Review the uploaded document and identify legal risks, gaps, or outdated clauses.",
            ),
        ),
        guidance_lines=(
            "- This is an analysis/review request for an uploaded document.",
            "- Ask only focused analysis questions that improve legal accuracy.",
            "- Do not switch into generic new-document drafting unless the user explicitly asks for it.",
        ),
    ),
    DocumentIntentPolicy(
        policy_id="document_modernization",
        phrases=(
            "update",
            "rebuild",
            "rewrite",
            "recreate",
            "fix",
            "correct document",
            "bring it up to date",
            "current law",
            "new law",
            "latest law",
            "old law",
            "outdated",
            "aktualiz",
            "prepracuj",
            "oprav",
            "podla noveho zakona",
            "podla aktualneho zakona",
            "stareho zakona",
            "nach aktuellem recht",
            "neuem recht",
            "aktualisieren",
            "uberarbeiten",
            "veralt",
        ),
        required_document_terms=_DOCUMENT_POLICY_REQUIRED_TERMS,
        tasks=(
            PlannedDocumentTask(
                task_id="review_uploaded_document",
                description="Review the uploaded document and identify relevant legal gaps or outdated clauses before any rewrite.",
            ),
            PlannedDocumentTask(
                task_id="update_based_on_current_law",
                description="If the uploaded document is outdated under current law, update or rebuild it before later tasks.",
            ),
        ),
        guidance_lines=(
            "- This is a document modernization request tied to current law.",
            "- Start by reviewing the uploaded document before deciding whether a rewrite is needed.",
            "- If current law requires changes, prepare the updated document before any requested summary.",
            "- Do not ask generic new-document intake questions when the uploaded document already contains the needed facts.",
        ),
    ),
    DocumentIntentPolicy(
        policy_id="document_summary",
        phrases=(
            "summary",
            "summar",
            "summarize",
            "summarise",
            "short summary",
            "sumar",
            "sumariz",
            "sumarizovanie",
            "zhrn",
            "zhrnut",
            "zusammenfass",
        ),
        required_document_terms=_DOCUMENT_POLICY_REQUIRED_TERMS,
        tasks=(
            PlannedDocumentTask(
                task_id="prepare_summary",
                description="Prepare the requested plain-language summary after completing any earlier document-review or update tasks.",
            ),
        ),
        guidance_lines=(
            "- This is a summary request for uploaded document content.",
            "- Start with a plain-language summary of the document contents in no more than 5 sentences.",
            "- Mention the main purpose, parties, dates, obligations, and obvious missing items if available.",
            "- If the user also asked for issues or risks, mention them only after the short summary.",
            "- Do not answer with validation metadata only.",
        ),
        requires_processed_documents=True,
    ),
)


def is_document_summary_request(query: str) -> bool:
    return query_matches_policy(query, policy_id="document_summary")


def is_document_analysis_request(query: str) -> bool:
    return query_matches_policy(query, policy_id="document_analysis")


def is_document_modernization_request(query: str) -> bool:
    return query_matches_policy(query, policy_id="document_modernization")


def normalize_document_intent_query(query: str) -> str:
    return " ".join(query.lower().split())


def query_matches_policy(query: str, *, policy_id: str) -> bool:
    normalized = normalize_document_intent_query(query)
    policy = next((item for item in _DOCUMENT_INTENT_POLICIES if item.policy_id == policy_id), None)
    if policy is None:
        return False
    if not any(term in normalized for term in policy.required_document_terms):
        return False
    return any(phrase in normalized for phrase in policy.phrases)


def match_document_intent_policies(query: str) -> tuple[DocumentPolicyMatch, ...]:
    normalized = normalize_document_intent_query(query)
    matches: list[DocumentPolicyMatch] = []
    for policy in _DOCUMENT_INTENT_POLICIES:
        if not any(term in normalized for term in policy.required_document_terms):
            continue
        hits = [normalized.find(phrase) for phrase in policy.phrases if phrase in normalized]
        if not hits:
            continue
        matches.append(DocumentPolicyMatch(policy=policy, position=min(hits)))
    return tuple(sorted(matches, key=lambda item: item.position))


def build_document_policy_plan(query: str) -> DocumentPolicyPlan:
    matches = match_document_intent_policies(query)
    ordered_policies = tuple(match.policy for match in matches)
    ordered_tasks: list[PlannedDocumentTask] = []
    seen_task_ids: set[str] = set()
    for policy in ordered_policies:
        for task in policy.tasks:
            if task.task_id in seen_task_ids:
                continue
            ordered_tasks.append(task)
            seen_task_ids.add(task.task_id)
    return DocumentPolicyPlan(
        ordered_policies=ordered_policies,
        ordered_tasks=tuple(ordered_tasks),
    )


def planned_document_tasks(query: str) -> list[PlannedDocumentTask]:
    return list(build_document_policy_plan(query).ordered_tasks)


def build_document_task_plan_note(
    *,
    query: str,
    has_processed_documents: bool,
) -> str:
    plan = build_document_policy_plan(query)
    if not plan.ordered_policies:
        return ""

    lines = [
        "",
        "",
        "DOCUMENT TASK PLAN MODE:",
        "- Use a single policy-driven legal agent response.",
        "- The user may have requested multiple document tasks in one message.",
        "- Execute the requested document tasks in the same order as the user's intent.",
        "- Do not skip earlier tasks before performing later tasks.",
        "- Ask only the minimum clarifying questions needed for the current active task.",
        "- Keep behavior policy-driven so future document policies/tasks can be added without changing the overall agent pattern.",
    ]
    lines.append("- Active policies in user-intent order:")
    for index, policy in enumerate(plan.ordered_policies, start=1):
        lines.append(f"  {index}. {policy.policy_id}")
        if policy.requires_processed_documents and not has_processed_documents:
            lines.append("     - The uploaded documents are not processed yet, so defer content-specific output until processed.")
            continue
        for guidance in policy.guidance_lines:
            lines.append(f"     {guidance}")
    if any(task.task_id == "prepare_summary" for task in plan.ordered_tasks):
        lines.append(
            "- If both update/rebuild and summary are requested, summarize the updated result unless the user clearly asked for the original document summary."
        )
    lines.append("- Planned task order:")
    for index, task in enumerate(plan.ordered_tasks, start=1):
        lines.append(f"  {index}. {task.task_id}: {task.description}")
    return "\n".join(lines)
