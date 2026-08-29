import importlib
import sys
import types


def _load_service_module():
    from app.document_templates.models import DocumentTemplateDefinition

    memory_module = types.ModuleType("langgraph.checkpoint.memory")

    class _InMemorySaver:
        pass

    memory_module.InMemorySaver = _InMemorySaver
    sys.modules["langgraph.checkpoint.memory"] = memory_module

    langgraph_checkpoint = types.ModuleType("langgraph.checkpoint")
    sys.modules["langgraph.checkpoint"] = langgraph_checkpoint

    langgraph_module = types.ModuleType("langgraph")
    sys.modules["langgraph"] = langgraph_module

    mcp_law_context = types.ModuleType("app.chat.mcp_law_context")
    mcp_law_context.build_mcp_law_context = lambda *args, **kwargs: None
    sys.modules["app.chat.mcp_law_context"] = mcp_law_context

    document_template_store = types.ModuleType("app.document_templates.store")

    class _DocumentTemplateNotFoundError(Exception):
        pass

    class _CaseTypeNotFoundError(Exception):
        pass

    class _FakeTemplateStore:
        def get(self, *, template_key: str, jurisdiction: str | None = None):
            if template_key != "sk.employment.employment_contract":
                raise _DocumentTemplateNotFoundError(template_key)
            return DocumentTemplateDefinition(
                template_id="seed-sk-employment-contract",
                template_key="sk.employment.employment_contract",
                lineage_key="seed-sk-employment-contract",
                jurisdiction=jurisdiction or "SK",
                language="sk-SK",
                category="Pracovne a personalne dokumenty",
                title="Pracovna zmluva",
                template_kind="employment_contract",
                description="test template",
                source_format="HTML",
                source_url="https://example.test/pracovna-zmluva",
                body=(
                    "PRACOVNÁ ZMLUVA\n\n"
                    "Článok I\n"
                    "Druh práce\n"
                    "Pozícia: {{job_position}}\n\n"
                    "Článok IV\n"
                    "Mzda\n"
                    "Zamestnávateľ: {{employer_business_name}}\n"
                    "Mzda: {{base_monthly_salary}}\n"
                ),
                keywords=("pracovna zmluva",),
                placeholders=(
                    "job_position",
                    "employer_business_name",
                    "base_monthly_salary",
                    "employee_full_name",
                    "employee_birth_date",
                    "employee_residence",
                    "place_of_work",
                    "start_date",
                    "employment_term_description",
                    "weekly_working_hours",
                    "employer_seat",
                    "employer_ico",
                    "employer_representative",
                    "job_description",
                ),
            )

        def find_best_match(self, *, request_text: str, country: str, template_kind: str | None = None):
            del country
            if template_kind == "employment_contract" and "pracovn" in request_text.lower():
                return 10, self.get(template_key="sk.employment.employment_contract", jurisdiction="SK")
            return 0, None

    document_template_store.CaseTypeNotFoundError = _CaseTypeNotFoundError
    document_template_store.DocumentTemplateNotFoundError = _DocumentTemplateNotFoundError
    document_template_store.DocumentTemplateStore = object
    document_template_store.get_document_template_store = lambda: _FakeTemplateStore()
    sys.modules["app.document_templates.store"] = document_template_store

    workflow_store = types.ModuleType("app.case_workflows.store")

    class _CaseWorkflowStore:
        pass

    class _WorkflowAssignmentNotFoundError(Exception):
        pass

    workflow_store.CaseWorkflowStore = _CaseWorkflowStore
    workflow_store.WorkflowAssignmentNotFoundError = _WorkflowAssignmentNotFoundError
    sys.modules["app.case_workflows.store"] = workflow_store

    agents_module = types.ModuleType("aijurisdictionagents.agents")
    agents_module.create_lawyer_agent = lambda *args, **kwargs: None
    sys.modules["aijurisdictionagents.agents"] = agents_module

    llm_routing = types.ModuleType("aijurisdictionagents.llm.routing")
    llm_routing.get_routed_llm_client = lambda *args, **kwargs: None
    sys.modules["aijurisdictionagents.llm.routing"] = llm_routing

    flow_packs_store = types.ModuleType("app.flow_packs.store")

    class _FlowPackNotFoundError(Exception):
        pass

    class _FlowPackStore:
        pass

    flow_packs_store.FlowPackNotFoundError = _FlowPackNotFoundError
    flow_packs_store.FlowPackStore = _FlowPackStore
    sys.modules["app.flow_packs.store"] = flow_packs_store

    orchestration_module = types.ModuleType("aijurisdictionagents.orchestration.case_workflow")
    orchestration_module.CaseWorkflowRuntime = object
    orchestration_module.CaseWorkflowState = dict
    orchestration_module.ReviewDisposition = str
    orchestration_module.build_initial_case_workflow_state = lambda **kwargs: kwargs
    sys.modules["aijurisdictionagents.orchestration.case_workflow"] = orchestration_module

    api_db_module = types.ModuleType("aijurisdictionagents.api_db")
    api_db_module.ApiDatabaseStore = object
    sys.modules["aijurisdictionagents.api_db"] = api_db_module

    schemas_module = types.ModuleType("aijurisdictionagents.schemas")
    schemas_module.Document = object
    schemas_module.Message = object
    sys.modules["aijurisdictionagents.schemas"] = schemas_module

    sys.modules.pop("app.case_workflows.service", None)
    return importlib.import_module("app.case_workflows.service")


def test_render_template_first_employment_draft_uses_managed_template() -> None:
    service = _load_service_module()

    rendered = service._render_template_first_employment_draft(
        {
            "jurisdiction": "SK",
            "language": "sk-SK",
            "case_type_key": "sk.employment.employment_contract",
            "request_text": "Priprav pracovnu zmluvu.",
            "verified_facts": {
                "employer_business_name": "Fiktíva Digital Solutions",
                "employer_seat": "Inovačná 18, 040 01 Košice",
                "employer_ico": "99 999 999",
                "employer_representative": "Ing. Martin Vzorový, konateľ",
                "employee_full_name": "Lucia Vzorová",
                "employee_birth_date": "14. februára 1994",
                "employee_birth_number": "945214/0000",
                "employee_residence": "Vzorová 27, 058 01 Poprad",
                "job_position": "AI vývojár / softvérový inžinier",
                "job_description": "Návrh, vývoj, testovanie a údržba softvérových riešení.",
                "place_of_work": "Inovačná 18, 040 01 Košice",
                "start_date": "1. októbra 2026",
                "employment_term_description": "pracovný pomer na dobu neurčitú",
                "probation_period": "3 mesiace",
                "base_monthly_salary": "3 200 EUR brutto",
                "weekly_working_hours": "40 hodín",
                "working_time_distribution": "pondelok až piatok",
                "vacation_entitlement": "v rozsahu podľa Zákonníka práce",
                "signature_place": "Košice",
                "signature_date": "15. septembra 2026",
                "employer_signatory_name": "Ing. Martin Vzorový",
                "employee_signatory_name": "Lucia Vzorová",
            },
        }
    )

    assert rendered is not None
    answer, template = rendered
    normalized = " ".join(answer.split()).lower()

    assert template.template_key == "sk.employment.employment_contract"
    assert "článok i" in normalized
    assert "článok iv" in normalized
    assert "fiktíva digital solutions" in normalized
