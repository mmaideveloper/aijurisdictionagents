from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any, Callable, Iterable, Mapping, Sequence

from ..agents.ai_web_search import EntityScreeningAgent

Validator = Callable[[str, Any], str | None]


@dataclass(frozen=True)
class ValidationIssue:
    field: str
    message: str
    severity: str = "error"


@dataclass(frozen=True)
class WorkflowStep:
    step_id: str
    name: str
    description: str
    tool_name: str | None = None
    required_inputs: tuple[str, ...] = ()
    output_artifacts: tuple[str, ...] = ()


@dataclass(frozen=True)
class WorkflowBlueprint:
    workflow_id: str
    country: str
    case_group: str
    description: str
    intent_keywords: tuple[str, ...]
    required_inputs: tuple[str, ...] = ()
    optional_inputs: tuple[str, ...] = ()
    input_validators: Mapping[str, Validator] = field(default_factory=dict)
    conflict_check_fields: tuple[str, ...] = ()
    mandatory_system_documents: tuple[str, ...] = ()
    steps: tuple[WorkflowStep, ...] = ()


@dataclass(frozen=True)
class WorkflowSelection:
    mode: str
    confidence: float
    reason: str
    workflow: WorkflowBlueprint | None = None
    missing_inputs: tuple[str, ...] = ()
    validation_issues: tuple[ValidationIssue, ...] = ()
    clarification_questions: tuple[str, ...] = ()
    required_documents: tuple[str, ...] = ()
    fact_conflicts: tuple["FactConflict", ...] = ()
    global_steps: tuple[str, ...] = ()
    screening_consent_prompt: str | None = None
    screening_task_prompt: str | None = None


@dataclass(frozen=True)
class FactConflict:
    field: str
    user_value: str
    system_value: str
    confirmation_question: str


class WorkflowRegistry:
    def __init__(self, workflows: Iterable[WorkflowBlueprint] | None = None) -> None:
        self._workflows: list[WorkflowBlueprint] = []
        if workflows is not None:
            for workflow in workflows:
                self.register(workflow)

    def register(self, workflow: WorkflowBlueprint) -> None:
        self._workflows.append(workflow)

    def for_country(self, country: str) -> list[WorkflowBlueprint]:
        normalized = country.strip().upper()
        return [workflow for workflow in self._workflows if workflow.country.upper() == normalized]


class WorkflowRouter:
    def __init__(self, registry: WorkflowRegistry, min_confidence: float = 0.35) -> None:
        self.registry = registry
        self.min_confidence = min_confidence

    def select(self, question: str, country: str, inputs: Mapping[str, Any]) -> tuple[WorkflowBlueprint | None, float]:
        candidates = self.registry.for_country(country)
        if not candidates:
            return None, 0.0
        lowered_question = question.lower()
        scored: list[tuple[WorkflowBlueprint, float]] = []
        for workflow in candidates:
            keyword_hits = sum(1 for keyword in workflow.intent_keywords if keyword.lower() in lowered_question)
            keyword_score = keyword_hits / max(len(workflow.intent_keywords), 1)
            required_hits = sum(1 for field in workflow.required_inputs if field in inputs and inputs[field] not in (None, ""))
            required_score = required_hits / max(len(workflow.required_inputs), 1)
            if keyword_hits > 0:
                base_intent_score = max(0.4, keyword_score)
            else:
                base_intent_score = 0.0
            score = min(1.0, base_intent_score + (required_score * 0.2))
            scored.append((workflow, score))

        scored.sort(key=lambda item: item[1], reverse=True)
        top_workflow, top_score = scored[0]
        if top_score < self.min_confidence:
            return None, top_score
        return top_workflow, top_score


class WorkflowEngine:
    def __init__(self, router: WorkflowRouter) -> None:
        self.router = router

    def plan_case(
        self,
        question: str,
        country: str,
        inputs: Mapping[str, Any],
        law_required_documents: Sequence[str] | None = None,
        external_facts: Mapping[str, Any] | None = None,
        user_requested_screening: bool = False,
        model_suggested_screening: bool = False,
        auto_detect_screening_intent: bool = True,
    ) -> WorkflowSelection:
        global_steps, screening_consent_prompt, screening_task_prompt = self._resolve_global_steps(
            question=question,
            country=country,
            inputs=inputs,
            user_requested_screening=user_requested_screening,
            model_suggested_screening=model_suggested_screening,
            auto_detect_screening_intent=auto_detect_screening_intent,
        )
        workflow, confidence = self.router.select(question, country, inputs)
        if workflow is None:
            return WorkflowSelection(
                mode="fallback",
                confidence=confidence,
                reason="No workflow met the minimum confidence threshold.",
                clarification_questions=(
                    "Prosím spresnite typ právneho prípadu (napr. zmena konateľa, prevod podielu, pracovná zmluva).",
                    "Uveďte krajinu a relevantné identifikačné údaje účastníkov.",
                ),
                required_documents=(),
                fact_conflicts=(),
                global_steps=global_steps,
                screening_consent_prompt=screening_consent_prompt,
                screening_task_prompt=screening_task_prompt,
            )

        missing_inputs = tuple(field for field in workflow.required_inputs if field not in inputs or inputs[field] in (None, ""))
        validation_issues = self._validate_inputs(workflow, inputs)
        clarification_questions = tuple(self._build_question(field) for field in missing_inputs)
        required_documents = self._resolve_required_documents(
            workflow=workflow,
            law_required_documents=law_required_documents,
        )
        fact_conflicts = self._detect_fact_conflicts(
            workflow=workflow,
            inputs=inputs,
            external_facts=external_facts,
        )
        if fact_conflicts:
            clarification_questions = clarification_questions + tuple(
                conflict.confirmation_question for conflict in fact_conflicts
            )
        return WorkflowSelection(
            mode="workflow",
            confidence=confidence,
            reason="Matched by intent and available input coverage.",
            workflow=workflow,
            missing_inputs=missing_inputs,
            validation_issues=validation_issues,
            clarification_questions=clarification_questions,
            required_documents=required_documents,
            fact_conflicts=fact_conflicts,
            global_steps=global_steps,
            screening_consent_prompt=screening_consent_prompt,
            screening_task_prompt=screening_task_prompt,
        )

    @staticmethod
    def _validate_inputs(
        workflow: WorkflowBlueprint,
        inputs: Mapping[str, Any],
    ) -> tuple[ValidationIssue, ...]:
        issues: list[ValidationIssue] = []
        for field_name, validator in workflow.input_validators.items():
            if field_name not in inputs:
                continue
            value = inputs[field_name]
            error = validator(field_name, value)
            if error:
                issues.append(ValidationIssue(field=field_name, message=error))
        return tuple(issues)

    @staticmethod
    def _build_question(field_name: str) -> str:
        return f"Prosím doplňte hodnotu pre pole '{field_name}'."

    @staticmethod
    def _resolve_required_documents(
        workflow: WorkflowBlueprint,
        law_required_documents: Sequence[str] | None,
    ) -> tuple[str, ...]:
        documents: list[str] = list(workflow.mandatory_system_documents)
        if law_required_documents:
            for document in law_required_documents:
                if document not in documents:
                    documents.append(document)
        return tuple(documents)

    @staticmethod
    def _detect_fact_conflicts(
        workflow: WorkflowBlueprint,
        inputs: Mapping[str, Any],
        external_facts: Mapping[str, Any] | None,
    ) -> tuple[FactConflict, ...]:
        if not external_facts:
            return ()
        conflicts: list[FactConflict] = []
        for field_name in workflow.conflict_check_fields:
            if field_name not in inputs or field_name not in external_facts:
                continue
            user_value = str(inputs[field_name]).strip()
            system_value = str(external_facts[field_name]).strip()
            if not user_value or not system_value:
                continue
            if user_value.casefold() != system_value.casefold():
                conflicts.append(
                    FactConflict(
                        field=field_name,
                        user_value=user_value,
                        system_value=system_value,
                        confirmation_question=(
                            f"Zadaná hodnota '{field_name}' je '{user_value}', "
                            f"ale v registri je '{system_value}'. Potvrďte, ktorá hodnota je platná."
                        ),
                    )
                )
        return tuple(conflicts)

    @staticmethod
    def _resolve_global_steps(
        *,
        question: str,
        country: str,
        inputs: Mapping[str, Any],
        user_requested_screening: bool,
        model_suggested_screening: bool,
        auto_detect_screening_intent: bool,
    ) -> tuple[tuple[str, ...], str | None, str | None]:
        screening_required = user_requested_screening or model_suggested_screening
        inferred_entity_type: str | None = None
        inferred_entity_value: str | None = None
        if auto_detect_screening_intent and not screening_required:
            screening_required, inferred_entity_type, inferred_entity_value = _infer_screening_from_question(question)
        if not screening_required:
            return (), None, None
        entity_type, entity_value = _pick_screening_entity(
            inputs=inputs,
            fallback_entity_type=inferred_entity_type,
            fallback_entity_value=inferred_entity_value,
        )
        if not entity_value:
            return ("global_entity_screening",), "Screening requested, but missing entity value for screening.", None
        screening_agent = EntityScreeningAgent()
        consent_prompt = screening_agent.build_screening_consent_prompt(
            entity_type=entity_type,
            entity_value=entity_value,
        )
        task_prompt = screening_agent.build_structured_screening_prompt(
            entity_type=entity_type,
            entity_value=entity_value,
            country=country,
        )
        return ("global_entity_screening",), consent_prompt, task_prompt


def _pick_screening_entity(
    *,
    inputs: Mapping[str, Any],
    fallback_entity_type: str | None = None,
    fallback_entity_value: str | None = None,
) -> tuple[str, str]:
    if "company_id" in inputs and str(inputs["company_id"]).strip():
        return "company", str(inputs["company_id"]).strip()
    if "person_name" in inputs and str(inputs["person_name"]).strip():
        return "person", str(inputs["person_name"]).strip()
    if "current_owner_name" in inputs and str(inputs["current_owner_name"]).strip():
        return "person", str(inputs["current_owner_name"]).strip()
    if fallback_entity_value:
        return (fallback_entity_type or "entity"), fallback_entity_value
    return "entity", ""


def _infer_screening_from_question(question: str) -> tuple[bool, str | None, str | None]:
    normalized = re.sub(r"\s+", " ", question.strip().lower())
    screening_markers = ("over mi", "over", "prever", "screening", "check")
    if not any(marker in normalized for marker in screening_markers):
        return False, None, None
    person_match = re.search(
        r"(?:over mi|over|prever)\s+(?P<name>[a-záäčďéíĺľňóôŕšťúýž]+\s+[a-záäčďéíĺľňóôŕšťúýž]+)",
        normalized,
        flags=re.IGNORECASE,
    )
    if person_match:
        return True, "person", person_match.group("name").strip().title()
    return True, None, None


def validate_slovak_company_id(_field_name: str, value: Any) -> str | None:
    normalized = str(value).strip()
    if not re.fullmatch(r"\d{8}", normalized):
        return "IČO musí mať presne 8 číslic."
    return None


def create_default_registry() -> WorkflowRegistry:
    return WorkflowRegistry(
        workflows=[
            WorkflowBlueprint(
                workflow_id="sk.company.add_co_owner.v1",
                country="SK",
                case_group="obchodne_pravo",
                description="Pridanie spoluvlastníka/spoločníka do s.r.o. vrátane prípravy dokumentov.",
                intent_keywords=(
                    "pridat spolocnika",
                    "pridat noveho spolocnika",
                    "novy spolocnik",
                    "zmena spolocnika",
                    "add co-owner",
                    "s.r.o.",
                ),
                required_inputs=("company_id", "current_owner_name", "new_co_owner_name", "ownership_share_percent", "effective_date"),
                optional_inputs=("new_co_owner_address", "purchase_price"),
                input_validators={"company_id": validate_slovak_company_id},
                conflict_check_fields=("current_owner_name",),
                mandatory_system_documents=(
                    "decision_of_general_meeting",
                    "general_meeting_minutes",
                ),
                steps=(
                    WorkflowStep(
                        step_id="verify_company_in_orsr",
                        name="Overenie spoločnosti v ORSR",
                        description="Overí existenciu spoločnosti, štatutára a aktuálnu štruktúru v ORSR.",
                        tool_name="orsr_lookup",
                        required_inputs=("company_id",),
                        output_artifacts=("company_verification_report",),
                    ),
                    WorkflowStep(
                        step_id="check_shareholder_constraints",
                        name="Kontrola obmedzení pre vstup nového spoločníka",
                        description="Skontroluje interné a zákonné obmedzenia pre zmenu spoločníka.",
                        tool_name="shareholder_structure_check",
                        required_inputs=("company_id", "new_co_owner_name", "ownership_share_percent"),
                        output_artifacts=("constraint_check_report",),
                    ),
                    WorkflowStep(
                        step_id="prepare_document_bundle",
                        name="Príprava balíka dokumentov",
                        description="Vygeneruje požadované dokumenty pre zápis zmeny v obchodnom registri.",
                        tool_name="document_bundle_generator",
                        required_inputs=("effective_date",),
                        output_artifacts=(
                            "decision_of_general_meeting",
                            "updated_articles_of_association",
                            "general_meeting_minutes",
                            "application_for_registry_update",
                        ),
                    ),
                ),
            ),
            WorkflowBlueprint(
                workflow_id="sk.company.verify_orsr.v1",
                country="SK",
                case_group="obchodne_pravo",
                description="Samostatné overenie obchodnej spoločnosti v ORSR.",
                intent_keywords=("overit firmu", "orsr", "obchodny register", "company verification"),
                required_inputs=("company_id",),
                input_validators={"company_id": validate_slovak_company_id},
                mandatory_system_documents=("company_verification_report",),
                steps=(
                    WorkflowStep(
                        step_id="verify_company_in_orsr",
                        name="Overenie spoločnosti v ORSR",
                        description="Overí základné údaje spoločnosti v ORSR.",
                        tool_name="orsr_lookup",
                        required_inputs=("company_id",),
                        output_artifacts=("company_verification_report",),
                    ),
                ),
            ),
        ]
    )
