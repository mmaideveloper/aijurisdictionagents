from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
from typing import TYPE_CHECKING, Any, Protocol
from uuid import UUID

from app.chat.models import Message, MessageRole, Session
from app.document_templates.store import DocumentTemplateStore

from aijurisdictionagents.agents import AICaseTypeDetectionAgent, CaseTypeCandidate
from aijurisdictionagents.api_db import ApiDatabaseStore, CaseCatalogSelection
from aijurisdictionagents.schemas import Document

if TYPE_CHECKING:
    from aijurisdictionagents.llm.routing import RoutedLLMClient


class _ResolvedCaseType(Protocol):
    name: str
    case_type_key: str
    prompt: Any
    templates: tuple[Any, ...]

_AUTO_PICK_CONFIDENCE = 0.72
_AUTO_PICK_MARGIN = 0.15
_DETECTION_SOURCE = "chat.case_type_detection_agent"


@dataclass(frozen=True)
class CaseCatalogContext:
    selection: CaseCatalogSelection | None = None
    prompt_note: str = ""
    template_documents: list[Document] = field(default_factory=list)
    direct_reply: str | None = None


@dataclass(frozen=True)
class CaseCatalogDetectionTrace:
    detection_text: str
    first_message_preview: str
    first_message_sha256: str


def resolve_case_catalog_context(
    *,
    session_id: UUID,
    session: Session,
    current_content: str,
    prior_messages: list[Message],
    route: RoutedLLMClient,
    store: ApiDatabaseStore,
    template_store: DocumentTemplateStore,
    document_generation_requested: bool,
) -> CaseCatalogContext:
    session_key = str(session_id)
    session_selection = store.get_case_catalog_selection(
        selection_scope="session",
        entity_id=session_key,
    )
    case_selection = _case_selection(store=store, case_id=(session.case_id or "").strip())
    active_selection = session_selection or case_selection
    should_detect = not prior_messages or _selection_needs_retry(active_selection)
    if should_detect:
        trace = _detection_trace(
            prior_messages=prior_messages,
            current_content=current_content,
            selection=active_selection,
        )
        active_selection = _detect_and_persist_case_type(
            session_id=session_key,
            session=session,
            detection_trace=trace,
            route=route,
            store=store,
            template_store=template_store,
        )
    if active_selection is None:
        return CaseCatalogContext()
    if (
        active_selection.status == "insufficient_sources"
        and document_generation_requested
        and active_selection.case_type_key
    ):
        return CaseCatalogContext(
            selection=active_selection,
            direct_reply=_insufficient_sources_reply(session=session, case_type_name=active_selection.case_type_name),
        )
    if active_selection.status == "ambiguous":
        return CaseCatalogContext(
            selection=active_selection,
            direct_reply=_clarification_reply(
                session=session,
                question=active_selection.clarification_question,
            ),
        )
    if not active_selection.case_type_key:
        return CaseCatalogContext(selection=active_selection)
    case_type = _safe_get_case_type(
        template_store=template_store,
        case_type_key=active_selection.case_type_key,
        jurisdiction=session.country,
    )
    if case_type is None:
        return CaseCatalogContext(selection=active_selection)
    prompt_note = _build_case_catalog_prompt_note(
        selection=active_selection,
        case_type_name=case_type.name,
        case_type_key=case_type.case_type_key,
        case_prompt_text=case_type.prompt.prompt_text if case_type.prompt is not None else "",
        template_titles=[item.title for item in case_type.templates],
    )
    template_documents = [
        _template_document(item.template_id, item.template_key, item.title, item.template_kind, item.description, item.body)
        for item in case_type.templates
    ]
    return CaseCatalogContext(
        selection=active_selection,
        prompt_note=prompt_note,
        template_documents=template_documents,
    )


def _detect_and_persist_case_type(
    *,
    session_id: str,
    session: Session,
    detection_trace: CaseCatalogDetectionTrace,
    route: RoutedLLMClient,
    store: ApiDatabaseStore,
    template_store: DocumentTemplateStore,
) -> CaseCatalogSelection | None:
    detection_text = detection_trace.detection_text
    ranked = template_store.rank_case_types(
        request_text=detection_text,
        country=session.country,
        limit=8,
    )
    if not ranked:
        selection = _upsert_selection(
            store=store,
            session_id=session_id,
            case_id=(session.case_id or "").strip(),
            selection_scope="session",
            entity_id=session_id,
            status="no_match",
            first_message_preview=detection_trace.first_message_preview,
            first_message_sha256=detection_trace.first_message_sha256,
        )
        _upsert_case_selection_from_session(store=store, selection=selection)
        _record_event(
            store=store,
            case_id=(session.case_id or "").strip(),
            session_id=session_id,
            event_type="case_type_detection.no_match",
            status="no_match",
            severity="info",
            summary="Automatic case-type detection found no matching case type.",
            details={"request_preview": detection_text[:180]},
        )
        return selection
    candidates = [
        CaseTypeCandidate(
            case_type_id=item.case_type_id,
            case_type_key=item.case_type_key,
            name=item.name,
            description=item.description,
            keywords=item.keywords,
            has_prompt=item.prompt is not None and bool(item.prompt.prompt_text.strip()),
            template_titles=tuple(template.title for template in item.templates),
        )
        for _score, item in ranked
    ]
    result = AICaseTypeDetectionAgent(route.client).detect(
        request_text=detection_text,
        country=session.country,
        candidates=candidates,
    )
    matched_case = next(
        (item for _score, item in ranked if item.case_type_key == (result.selected_case_type_key or "")),
        None,
    )
    confidence_gap = max(0.0, result.confidence - result.second_confidence)
    if (
        result.status != "matched"
        or matched_case is None
        or result.confidence < _AUTO_PICK_CONFIDENCE
        or confidence_gap < _AUTO_PICK_MARGIN
    ):
        clarification_question = result.clarification_question.strip() or _default_clarification_question(
            session=session,
            ranked=ranked,
        )
        selection = _upsert_selection(
            store=store,
            session_id=session_id,
            case_id=(session.case_id or "").strip(),
            selection_scope="session",
            entity_id=session_id,
            case_type_id=matched_case.case_type_id if matched_case is not None else "",
            case_type_key=matched_case.case_type_key if matched_case is not None else "",
            case_type_name=matched_case.name if matched_case is not None else "",
            status="ambiguous",
            confidence_score=result.confidence,
            confidence_gap=confidence_gap,
            first_message_preview=detection_trace.first_message_preview,
            first_message_sha256=detection_trace.first_message_sha256,
            clarification_question=clarification_question,
        )
        _upsert_case_selection_from_session(store=store, selection=selection)
        _record_event(
            store=store,
            case_id=(session.case_id or "").strip(),
            session_id=session_id,
            event_type="case_type_detection.ambiguous",
            status="ambiguous",
            severity="info",
            summary="Automatic case-type detection needs clarification before a workflow can be selected.",
            details={
                "selected_case_type_key": result.selected_case_type_key,
                "confidence": result.confidence,
                "second_case_type_key": result.second_case_type_key,
                "second_confidence": result.second_confidence,
                "clarification_question": clarification_question,
                "rationale": result.rationale,
            },
        )
        return selection
    prompt_ids = [matched_case.prompt.case_prompt_id] if matched_case.prompt is not None else []
    template_ids = [item.template_id for item in matched_case.templates]
    template_keys = [item.template_key for item in matched_case.templates]
    status = _selection_status(prompt_ids=prompt_ids, template_ids=template_ids)
    selection = _upsert_selection(
        store=store,
        session_id=session_id,
        case_id=(session.case_id or "").strip(),
        selection_scope="session",
        entity_id=session_id,
        case_type_id=matched_case.case_type_id,
        case_type_key=matched_case.case_type_key,
        case_type_name=matched_case.name,
        prompt_ids=prompt_ids,
        template_ids=template_ids,
        template_keys=template_keys,
        status=status,
        confidence_score=result.confidence,
        confidence_gap=confidence_gap,
        first_message_preview=detection_trace.first_message_preview,
        first_message_sha256=detection_trace.first_message_sha256,
    )
    _upsert_case_selection_from_session(store=store, selection=selection)
    _record_event(
        store=store,
        case_id=(session.case_id or "").strip(),
        session_id=session_id,
        event_type="case_type_detection.matched",
        status=status,
        severity="info",
        summary=f"Automatic case-type detection selected {matched_case.case_type_key}.",
        details={
            "case_type_id": matched_case.case_type_id,
            "case_type_key": matched_case.case_type_key,
            "case_type_name": matched_case.name,
            "confidence": result.confidence,
            "confidence_gap": confidence_gap,
            "prompt_ids": prompt_ids,
            "template_ids": template_ids,
            "template_keys": template_keys,
            "rationale": result.rationale,
        },
    )
    if status == "insufficient_sources":
        _record_event(
            store=store,
            case_id=(session.case_id or "").strip(),
            session_id=session_id,
            event_type="case_type_detection.insufficient_sources",
            status=status,
            severity="warning",
            summary=f"Case type {matched_case.case_type_key} has no linked prompts or templates.",
            details={"case_type_key": matched_case.case_type_key},
        )
    elif status == "template_missing":
        _record_event(
            store=store,
            case_id=(session.case_id or "").strip(),
            session_id=session_id,
            event_type="case_type_detection.template_missing",
            status=status,
            severity="warning",
            summary=f"Case type {matched_case.case_type_key} has prompts but no linked templates.",
            details={"case_type_key": matched_case.case_type_key, "prompt_ids": prompt_ids},
        )
    elif status == "prompt_missing":
        _record_event(
            store=store,
            case_id=(session.case_id or "").strip(),
            session_id=session_id,
            event_type="case_type_detection.prompt_missing",
            status=status,
            severity="warning",
            summary=f"Case type {matched_case.case_type_key} has templates but no linked prompts.",
            details={"case_type_key": matched_case.case_type_key, "template_ids": template_ids},
        )
    return selection


def _selection_status(*, prompt_ids: list[str], template_ids: list[str]) -> str:
    if not prompt_ids and not template_ids:
        return "insufficient_sources"
    if prompt_ids and not template_ids:
        return "template_missing"
    if template_ids and not prompt_ids:
        return "prompt_missing"
    return "matched"


def _upsert_selection(
    *,
    store: ApiDatabaseStore,
    session_id: str,
    case_id: str,
    selection_scope: str,
    entity_id: str,
    case_type_id: str = "",
    case_type_key: str = "",
    case_type_name: str = "",
    prompt_ids: list[str] | tuple[str, ...] = (),
    template_ids: list[str] | tuple[str, ...] = (),
    template_keys: list[str] | tuple[str, ...] = (),
    status: str,
    confidence_score: float = 0.0,
    confidence_gap: float = 0.0,
    first_message_preview: str = "",
    first_message_sha256: str = "",
    clarification_question: str = "",
) -> CaseCatalogSelection:
    return store.upsert_case_catalog_selection(
        selection_scope=selection_scope,
        entity_id=entity_id,
        case_id=case_id,
        session_id=session_id,
        case_type_id=case_type_id,
        case_type_key=case_type_key,
        case_type_name=case_type_name,
        prompt_ids=prompt_ids,
        template_ids=template_ids,
        template_keys=template_keys,
        status=status,
        confidence_score=confidence_score,
        confidence_gap=confidence_gap,
        source=_DETECTION_SOURCE,
        first_message_preview=first_message_preview,
        first_message_sha256=first_message_sha256,
        clarification_question=clarification_question,
    )


def _upsert_case_selection_from_session(
    *,
    store: ApiDatabaseStore,
    selection: CaseCatalogSelection,
) -> None:
    if not selection.case_id:
        return
    store.upsert_case_catalog_selection(
        selection_scope="case",
        entity_id=selection.case_id,
        case_id=selection.case_id,
        session_id=selection.session_id,
        case_type_id=selection.case_type_id,
        case_type_key=selection.case_type_key,
        case_type_name=selection.case_type_name,
        prompt_ids=list(selection.prompt_ids),
        template_ids=list(selection.template_ids),
        template_keys=list(selection.template_keys),
        status=selection.status,
        confidence_score=selection.confidence_score,
        confidence_gap=selection.confidence_gap,
        source=selection.source,
        first_message_preview=selection.first_message_preview,
        first_message_sha256=selection.first_message_sha256,
        clarification_question=selection.clarification_question,
    )


def _record_event(
    *,
    store: ApiDatabaseStore,
    case_id: str,
    session_id: str,
    event_type: str,
    status: str,
    severity: str,
    summary: str,
    details: dict[str, Any],
) -> None:
    store.record_case_catalog_event(
        case_id=case_id,
        session_id=session_id,
        event_type=event_type,
        status=status,
        severity=severity,
        summary=summary,
        details=details,
    )


def _case_selection(*, store: ApiDatabaseStore, case_id: str) -> CaseCatalogSelection | None:
    if not case_id:
        return None
    return store.get_case_catalog_selection(selection_scope="case", entity_id=case_id)


def _selection_needs_retry(selection: CaseCatalogSelection | None) -> bool:
    if selection is None:
        return True
    return selection.status in {"ambiguous", "no_match"}


def _detection_text(*, prior_messages: list[Message], current_content: str) -> str:
    user_texts = [
        message.content.strip()
        for message in prior_messages
        if message.role == MessageRole.USER and message.content.strip()
    ]
    user_texts.append(current_content.strip())
    return "\n".join(text for text in user_texts if text)


def _detection_trace(
    *,
    prior_messages: list[Message],
    current_content: str,
    selection: CaseCatalogSelection | None,
) -> CaseCatalogDetectionTrace:
    detection_text = _detection_text(prior_messages=prior_messages, current_content=current_content)
    if selection is not None and selection.first_message_sha256.strip():
        return CaseCatalogDetectionTrace(
            detection_text=detection_text,
            first_message_preview=selection.first_message_preview,
            first_message_sha256=selection.first_message_sha256,
        )
    first_message_preview = _first_user_message_text(
        prior_messages=prior_messages,
        current_content=current_content,
    )
    first_message_sha256 = (
        hashlib.sha256(first_message_preview.strip().encode("utf-8")).hexdigest()
        if first_message_preview.strip()
        else ""
    )
    return CaseCatalogDetectionTrace(
        detection_text=detection_text,
        first_message_preview=first_message_preview,
        first_message_sha256=first_message_sha256,
    )


def _first_user_message_text(*, prior_messages: list[Message], current_content: str) -> str:
    for message in prior_messages:
        if message.role == MessageRole.USER and message.content.strip():
            return message.content.strip()
    return current_content.strip()


def _default_clarification_question(
    *,
    session: Session,
    ranked: list[tuple[int, Any]],
) -> str:
    top_names = [item.name for _score, item in ranked[:2] if str(item.name).strip()]
    if len(top_names) >= 2:
        return _localize(
            session=session,
            sk=f"Potrebujem upresniť, či ide skôr o {top_names[0]}, alebo o {top_names[1]}. Aký dokument alebo výsledok chcete pripraviť?",
            en=f"I need to clarify whether this is closer to {top_names[0]} or {top_names[1]}. What document or outcome do you want to prepare?",
            de=f"Ich muss klären, ob es eher um {top_names[0]} oder um {top_names[1]} geht. Welches Dokument oder Ergebnis möchten Sie vorbereiten?",
        )
    return _localize(
        session=session,
        sk="Potrebujem ešte jedno upresnenie, aby som vybral správny typ prípadu. Aký dokument alebo právny výsledok chcete pripraviť?",
        en="I need one more clarification to choose the right case type. What document or legal outcome do you want to prepare?",
        de="Ich brauche noch eine Klarstellung, um den richtigen Falltyp zu wählen. Welches Dokument oder rechtliche Ergebnis möchten Sie vorbereiten?",
    )


def _clarification_reply(*, session: Session, question: str) -> str:
    prompt = question.strip() or _default_clarification_question(session=session, ranked=[])
    return _localize(
        session=session,
        sk=f"Na automatické určenie správneho workflowu potrebujem ešte jedno upresnenie.\n\n{prompt}",
        en=f"I need one more clarification before I can select the right workflow automatically.\n\n{prompt}",
        de=f"Ich brauche noch eine Klarstellung, bevor ich den richtigen Workflow automatisch auswählen kann.\n\n{prompt}",
    )


def _insufficient_sources_reply(*, session: Session, case_type_name: str) -> str:
    label = case_type_name.strip() or _localize(session=session, sk="tento typ prípadu", en="this case type", de="diesen Falltyp")
    return _localize(
        session=session,
        sk=f"Identifikoval som typ prípadu {label}, ale v internom katalógu k nemu zatiaľ nie sú dostupné dostatočné zdroje ani šablóny. Návrh dokumentu preto teraz nie je možné bezpečne pripraviť. Administrátor bol o tomto nedostatku zaznamenaný v auditnej evidencii.",
        en=f"I identified the case type {label}, but the internal catalog does not yet contain enough sources or templates for it. A document draft cannot be prepared safely right now. This gap has been recorded for the administrator in the audit log.",
        de=f"Ich habe den Falltyp {label} identifiziert, aber der interne Katalog enthält dafür noch nicht genügend Quellen oder Vorlagen. Ein Dokumententwurf kann deshalb derzeit nicht sicher erstellt werden. Diese Lücke wurde für den Administrator im Auditprotokoll erfasst.",
    )


def _build_case_catalog_prompt_note(
    *,
    selection: CaseCatalogSelection,
    case_type_name: str,
    case_type_key: str,
    case_prompt_text: str,
    template_titles: list[str],
) -> str:
    lines = [
        "AUTOMATIC CASE-TYPE DETECTION:",
        f"- Selected case type: {case_type_name} ({case_type_key}).",
        f"- Detection confidence: {selection.confidence_score:.2f}.",
        f"- Detection source: {_DETECTION_SOURCE}.",
    ]
    if selection.status == "template_missing":
        lines.append("- Admin gap logged: linked template is missing, so use the matched case prompt only.")
    elif selection.status == "prompt_missing":
        lines.append("- Admin gap logged: linked prompt is missing, so use the matched templates only.")
    elif selection.status == "matched":
        lines.append("- Use the matched case prompt and templates as the primary drafting guidance for this case type.")
    if case_prompt_text.strip():
        lines.extend(["", "MATCHED CASE PROMPT:", case_prompt_text.strip()])
    if template_titles:
        lines.extend(["", "MATCHED TEMPLATE TITLES:"])
        lines.extend(f"- {title}" for title in template_titles)
    lines.extend(
        [
            "",
            "COMPLIANCE NOTE:",
            "- Do not claim more certainty than the catalog supports.",
            "- If required facts are still missing, ask exactly one focused clarification question.",
            "- Keep human oversight visible for legal-risk drafting outputs.",
        ]
    )
    return "\n".join(lines)


def _template_document(
    template_id: str,
    template_key: str,
    title: str,
    template_kind: str,
    description: str,
    body: str,
) -> Document:
    lines = [
        f"Template title: {title}",
        f"Template key: {template_key}",
        f"Template kind: {template_kind}",
        f"Description: {description}",
    ]
    if body.strip():
        lines.extend(["", "Template body:", body.strip()])
    return Document(
        doc_id=template_id,
        path=f"case-templates/{template_key}.txt",
        content="\n".join(lines).strip(),
    )


def _safe_get_case_type(
    *,
    template_store: DocumentTemplateStore,
    case_type_key: str,
    jurisdiction: str,
) -> _ResolvedCaseType | None:
    try:
        return template_store.get_case_type(case_type_key=case_type_key, jurisdiction=jurisdiction)
    except KeyError:
        return None


def _localize(*, session: Session, sk: str, en: str, de: str) -> str:
    language = (session.language or "").strip().lower()
    if language.startswith("de"):
        return de
    if language.startswith("en"):
        return en
    return sk
