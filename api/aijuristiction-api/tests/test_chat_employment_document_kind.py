import importlib
import sys
import types


def _load_chat_api():
    stubbed_modules: dict[str, types.ModuleType] = {}
    original_modules = {name: sys.modules.get(name) for name in (
        "app.chat.core_runtime",
        "app.chat.case_type_detection",
        "app.chat.country_services",
        "app.flow_packs.api",
        "app.chat.intent_policy_service",
        "app.chat.mcp_law_context",
        "app.chat.mcp_status_context",
        "app.chat.output_validation",
        "app.chat.result_metadata",
        "app.case_workflows.service",
        "app.security",
        "app.services.email_scheduler",
        "aijurisdictionagents.llm",
        "aijurisdictionagents.llm.base",
        "aijurisdictionagents.llm.routing",
        "services.document_processor.runtime",
        "services.document_processor.service",
    )}

    core_runtime = types.ModuleType("app.chat.core_runtime")
    core_runtime.core_message_role = lambda *args, **kwargs: "assistant"
    core_runtime.run_orchestration = lambda *args, **kwargs: None
    stubbed_modules["app.chat.core_runtime"] = core_runtime

    case_type_detection = types.ModuleType("app.chat.case_type_detection")
    case_type_detection.resolve_case_catalog_context = lambda *args, **kwargs: None
    stubbed_modules["app.chat.case_type_detection"] = case_type_detection

    country_services = types.ModuleType("app.chat.country_services")
    country_services.prepare_country_direct_reply = lambda *args, **kwargs: None
    stubbed_modules["app.chat.country_services"] = country_services

    flow_packs_api = types.ModuleType("app.flow_packs.api")
    flow_packs_api.get_flow_pack_store = lambda *args, **kwargs: None
    stubbed_modules["app.flow_packs.api"] = flow_packs_api

    intent_policy = types.ModuleType("app.chat.intent_policy_service")
    intent_policy.build_document_task_plan_note = lambda *args, **kwargs: ""
    intent_policy.is_document_modernization_request = lambda *args, **kwargs: False
    stubbed_modules["app.chat.intent_policy_service"] = intent_policy

    mcp_law_context = types.ModuleType("app.chat.mcp_law_context")
    mcp_law_context.build_mcp_law_context = lambda *args, **kwargs: None
    stubbed_modules["app.chat.mcp_law_context"] = mcp_law_context

    mcp_status_context = types.ModuleType("app.chat.mcp_status_context")
    mcp_status_context.build_mcp_status_context = lambda *args, **kwargs: None
    stubbed_modules["app.chat.mcp_status_context"] = mcp_status_context

    output_validation = types.ModuleType("app.chat.output_validation")

    class _ValidationAgent:
        def __init__(self, *args, **kwargs) -> None:
            pass

    class _LawyerOutputUserProfile:
        pass

    output_validation.AILawyerOutputMessageValidationAgent = _ValidationAgent
    output_validation.LawyerOutputUserProfile = _LawyerOutputUserProfile
    stubbed_modules["app.chat.output_validation"] = output_validation

    result_metadata = types.ModuleType("app.chat.result_metadata")
    result_metadata.build_session_result_metadata = lambda *args, **kwargs: {}
    stubbed_modules["app.chat.result_metadata"] = result_metadata

    service_module = types.ModuleType("app.case_workflows.service")
    service_module.handle_active_chat_workflow_turn = lambda *args, **kwargs: None
    service_module.handle_chat_workflow_turn = lambda *args, **kwargs: None
    service_module.workflow_user_reply = lambda *args, **kwargs: None
    stubbed_modules["app.case_workflows.service"] = service_module

    security_module = types.ModuleType("app.security")

    def _require_api_key() -> None:
        return None

    security_module.require_api_key = _require_api_key
    stubbed_modules["app.security"] = security_module

    email_scheduler = types.ModuleType("app.services.email_scheduler")

    class _EmailScheduler:
        pass

    email_scheduler.EmailScheduler = _EmailScheduler
    stubbed_modules["app.services.email_scheduler"] = email_scheduler

    llm_module = types.ModuleType("aijurisdictionagents.llm")
    llm_module.get_embedding_client = lambda *args, **kwargs: None
    stubbed_modules["aijurisdictionagents.llm"] = llm_module

    llm_base = types.ModuleType("aijurisdictionagents.llm.base")

    class _ModelProcessingTimeout(Exception):
        pass

    llm_base.ModelProcessingTimeout = _ModelProcessingTimeout
    llm_base.read_positive_finite_env_seconds = lambda *args, **kwargs: 1.0
    stubbed_modules["aijurisdictionagents.llm.base"] = llm_base

    llm_routing = types.ModuleType("aijurisdictionagents.llm.routing")

    class _ModelRouteUnavailable(Exception):
        pass

    class _RoutedLLMClient:
        pass

    llm_routing.ModelRouteUnavailable = _ModelRouteUnavailable
    llm_routing.RoutedLLMClient = _RoutedLLMClient
    llm_routing.get_routed_llm_client = lambda *args, **kwargs: None
    stubbed_modules["aijurisdictionagents.llm.routing"] = llm_routing

    processor_runtime = types.ModuleType("services.document_processor.runtime")
    processor_runtime.cosine_similarity = lambda *args, **kwargs: 0.0
    processor_runtime.lexical_overlap_score = lambda *args, **kwargs: 0.0
    processor_runtime.parse_embedding_vector = lambda *args, **kwargs: []
    stubbed_modules["services.document_processor.runtime"] = processor_runtime

    processor_service = types.ModuleType("services.document_processor.service")

    class _DocumentProcessor:
        pass

    processor_service.DocumentProcessor = _DocumentProcessor
    stubbed_modules["services.document_processor.service"] = processor_service

    try:
        sys.modules.update(stubbed_modules)
        sys.modules.pop("app.chat.api", None)
        return importlib.import_module("app.chat.api")
    finally:
        for name, module in original_modules.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module


def test_detect_document_kind_recognizes_employment_contract() -> None:
    chat_api = _load_chat_api()

    document_kind = chat_api._detect_document_kind(
        [
            "Pracovná zmluva",
            "Zamestnávateľ: Fiktíva Digital Solutions",
            "Zamestnanec: Lucia Vzorová",
            "Druh pracovného pomeru: pracovný pomer na dobu neurčitú",
        ],
        None,
    )

    assert document_kind == "employment_contract"


def test_extract_document_facts_from_employment_questionnaire() -> None:
    chat_api = _load_chat_api()

    facts = chat_api._extract_document_facts(
        [
            "1. Zamestnávateľ",
            "Obchodné meno: Fiktíva Digital Solutions",
            "Sídlo: Inovačná 18, 040 01 Košice",
            "IČO: 99 999 999",
            "Zastúpený: Ing. Martin Vzorový, konateľ",
            "E-mail: personalne@fiktiva-example.sk",
            "Telefón: +421 900 000 000",
            "2. Zamestnanec",
            "Meno a priezvisko: Lucia Vzorová",
            "Dátum narodenia: 14. februára 1994",
            "Rodné číslo: 945214/0000",
            "Trvalý pobyt: Vzorová 27, 058 01 Poprad",
            "Číslo občianskeho preukazu: TEST000001",
            "E-mail: lucia.vzorova@example.com",
            "Telefón: +421 900 000 111",
            "3. Údaje o pracovnom pomere",
            "Druh pracovného pomeru: pracovný pomer na dobu neurčitú",
            "Deň nástupu do práce: 1. októbra 2026",
            "Pracovná pozícia: AI vývojár / softvérový inžinier",
            "Druh práce: Návrh, vývoj, testovanie a údržba softvérových riešení.",
            "Miesto výkonu práce: Inovačná 18, 040 01 Košice.",
            "Skúšobná doba: 3 mesiace",
            "4. Pracovný čas",
            "Týždenný pracovný čas: 40 hodín",
            "Rozvrhnutie pracovného času: pondelok až piatok",
            "5. Mzdové podmienky",
            "Základná mesačná mzda: 3 200 EUR brutto",
            "Variabilná zložka mzdy: do 10 % základnej mesačnej mzdy",
            "Výplatný termín: najneskôr 15. deň kalendárneho mesiaca",
            "Spôsob vyplácania mzdy: bezhotovostným prevodom na účet zamestnanca",
            "6. Ďalšie pracovné podmienky",
            "Dovolenka: v rozsahu podľa Zákonníka práce",
            "Miesto uzatvorenia pracovnej zmluvy: Košice",
            "Dátum uzatvorenia pracovnej zmluvy: 15. septembra 2026",
            "Za zamestnávateľa:",
            "Ing. Martin Vzorový",
            "Zamestnanec:",
            "Lucia Vzorová",
        ]
    )

    assert facts["employer_business_name"] == "Fiktíva Digital Solutions"
    assert facts["employee_full_name"] == "Lucia Vzorová"
    assert facts["job_position"] == "AI vývojár / softvérový inžinier"
    assert facts["base_monthly_salary"] == "3 200 EUR brutto"
    assert facts["signature_place"] == "Košice"


def test_build_document_asset_content_renders_employment_contract_template() -> None:
    chat_api = _load_chat_api()

    title, lines = chat_api._build_document_asset_content(
        entry={"type": "contract"},
        document_kind="employment_contract",
        facts={
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
        country="SK",
        language="sk-SK",
        law_citation_lines=[],
        fallback_index=1,
    )

    normalized = chat_api._canonicalize_document_text(" ".join(lines))

    assert title == "Pracovna zmluva"
    assert "clanok i" in normalized
    assert "clanok iv" in normalized
    assert "fiktiva digital solutions" in normalized
    assert "ai vyvojar / softverovy inzinier" in normalized
