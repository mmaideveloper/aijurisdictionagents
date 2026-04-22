from aijurisdictionagents.workflows import WorkflowEngine, WorkflowRouter, create_default_registry


def test_router_selects_add_co_owner_workflow() -> None:
    engine = WorkflowEngine(WorkflowRouter(create_default_registry()))

    result = engine.plan_case(
        question="Chcem pridat noveho spolocnika do s.r.o. a pripravit podklady.",
        country="SK",
        inputs={
            "company_id": "12345678",
            "current_owner_name": "Peter Novak",
            "new_co_owner_name": "Jan Novak",
            "ownership_share_percent": "25",
            "effective_date": "2026-04-30",
        },
    )

    assert result.mode == "workflow"
    assert result.workflow is not None
    assert result.workflow.workflow_id == "sk.company.add_co_owner.v1"
    assert result.confidence > 0.35
    assert result.validation_issues == ()
    assert result.workflow.steps
    assert result.workflow.steps[0].step_id == "verify_company_in_orsr"
    assert result.required_documents == ("decision_of_general_meeting", "general_meeting_minutes")
    assert result.global_steps == ()
    assert result.screening_consent_prompt is None
    assert result.screening_task_prompt is None


def test_router_selects_verify_company_workflow() -> None:
    engine = WorkflowEngine(WorkflowRouter(create_default_registry()))

    result = engine.plan_case(
        question="Chcem overit firmu v ORSR podla ICO.",
        country="SK",
        inputs={"company_id": "12345678"},
    )

    assert result.mode == "workflow"
    assert result.workflow is not None
    assert result.workflow.workflow_id == "sk.company.verify_orsr.v1"
    assert result.required_documents == ("company_verification_report",)


def test_engine_requests_missing_required_inputs() -> None:
    engine = WorkflowEngine(WorkflowRouter(create_default_registry()))

    result = engine.plan_case(
        question="Potrebujem pridat spolocnika v s.r.o.",
        country="SK",
        inputs={"company_id": "12345678"},
    )

    assert result.mode == "workflow"
    assert result.workflow is not None
    assert result.workflow.workflow_id == "sk.company.add_co_owner.v1"
    assert set(result.missing_inputs) == {"current_owner_name", "new_co_owner_name", "ownership_share_percent", "effective_date"}
    assert len(result.clarification_questions) == 4
    assert result.required_documents == ("decision_of_general_meeting", "general_meeting_minutes")


def test_engine_detects_invalid_company_id() -> None:
    engine = WorkflowEngine(WorkflowRouter(create_default_registry()))

    result = engine.plan_case(
        question="Chcem pridat spolocnika a skontrolovat ORSR.",
        country="SK",
        inputs={"company_id": "123"},
    )

    assert result.mode == "workflow"
    assert result.validation_issues
    assert result.validation_issues[0].field == "company_id"


def test_engine_merges_mandatory_and_law_required_documents() -> None:
    engine = WorkflowEngine(WorkflowRouter(create_default_registry()))

    result = engine.plan_case(
        question="Chcem pridat noveho spolocnika do s.r.o.",
        country="SK",
        inputs={
            "company_id": "12345678",
            "current_owner_name": "Peter Novak",
            "new_co_owner_name": "Jan Novak",
            "ownership_share_percent": "25",
            "effective_date": "2026-04-30",
        },
        law_required_documents=("beneficial_owner_declaration", "general_meeting_minutes"),
    )

    assert result.mode == "workflow"
    assert result.required_documents == (
        "decision_of_general_meeting",
        "general_meeting_minutes",
        "beneficial_owner_declaration",
    )


def test_engine_creates_confirmation_question_when_owner_conflicts_with_registry() -> None:
    engine = WorkflowEngine(WorkflowRouter(create_default_registry()))
    result = engine.plan_case(
        question="Chcem pridat noveho spolocnika do s.r.o.",
        country="SK",
        inputs={
            "company_id": "12345678",
            "current_owner_name": "Peter Novak",
            "new_co_owner_name": "Jan Novak",
            "ownership_share_percent": "25",
            "effective_date": "2026-04-30",
        },
        external_facts={"current_owner_name": "Martin Novak"},
    )

    assert result.mode == "workflow"
    assert result.fact_conflicts
    assert result.fact_conflicts[0].field == "current_owner_name"
    assert "Potvrďte, ktorá hodnota je platná." in result.clarification_questions[-1]


def test_engine_uses_fallback_when_no_workflow_matches() -> None:
    engine = WorkflowEngine(WorkflowRouter(create_default_registry()))

    result = engine.plan_case(
        question="Potrebujem radu o rozvode a starostlivosti o dieta.",
        country="SK",
        inputs={"party_a": "Jana"},
    )

    assert result.mode == "fallback"
    assert result.workflow is None
    assert result.clarification_questions
    assert result.required_documents == ()
    assert result.fact_conflicts == ()
    assert result.global_steps == ()
    assert result.screening_consent_prompt is None
    assert result.screening_task_prompt is None


def test_engine_adds_global_screening_step_when_user_requests_it() -> None:
    engine = WorkflowEngine(WorkflowRouter(create_default_registry()))
    result = engine.plan_case(
        question="Chcem pridat noveho spolocnika do s.r.o.",
        country="SK",
        inputs={
            "company_id": "12345678",
            "current_owner_name": "Peter Novak",
            "new_co_owner_name": "Jan Novak",
            "ownership_share_percent": "25",
            "effective_date": "2026-04-30",
        },
        user_requested_screening=True,
    )

    assert result.mode == "workflow"
    assert result.global_steps == ("global_entity_screening",)
    assert result.screening_consent_prompt is not None
    assert "Reply YES to continue or NO to skip." in result.screening_consent_prompt
    assert result.screening_task_prompt is not None
    assert "registered address" in result.screening_task_prompt


def test_engine_adds_global_screening_step_when_model_suggests_it() -> None:
    engine = WorkflowEngine(WorkflowRouter(create_default_registry()))
    result = engine.plan_case(
        question="Chcem overit firmu v ORSR podla ICO.",
        country="SK",
        inputs={"company_id": "12345678"},
        model_suggested_screening=True,
    )

    assert result.mode == "workflow"
    assert result.global_steps == ("global_entity_screening",)
    assert result.screening_consent_prompt is not None
    assert result.screening_task_prompt is not None


def test_engine_auto_detects_slovak_screening_request_and_extracts_person() -> None:
    engine = WorkflowEngine(WorkflowRouter(create_default_registry()))
    result = engine.plan_case(
        question="Over mi jana hraska",
        country="SK",
        inputs={},
    )

    assert result.global_steps == ("global_entity_screening",)
    assert result.screening_consent_prompt is not None
    assert "person = 'Jana Hraska'" in result.screening_consent_prompt
    assert result.screening_task_prompt is not None
    assert "list of trade licenses / sole-trader businesses" in result.screening_task_prompt


def test_router_selects_car_validation_workflow_for_car_queries() -> None:
    engine = WorkflowEngine(WorkflowRouter(create_default_registry()))

    result = engine.plan_case(
        question="Overit auto podla VIN WP0ZZZ99ZTS392124 a SPZ BA123AB",
        country="SK",
        inputs={"vin": "WP0ZZZ99ZTS392124", "spz": "BA123AB"},
    )

    assert result.mode == "workflow"
    assert result.workflow is not None
    assert result.workflow.workflow_id == "sk.car.verify_vehicle.v1"
    assert result.required_documents == ("vehicle_verification_report",)
    assert "pátracie evidencie" in result.workflow.steps[0].description
