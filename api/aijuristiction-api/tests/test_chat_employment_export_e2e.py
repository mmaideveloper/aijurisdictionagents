from __future__ import annotations

from fastapi import FastAPI
from io import BytesIO
import importlib
import sys
import types
import unicodedata

from fastapi.testclient import TestClient
from pypdf import PdfReader

AUTH_HEADERS = {"x-api-key": "aijuris"}


def _pdf_text(content: bytes) -> str:
    return "\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(content)).pages)


def _canonical_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    plain = "".join(char for char in normalized if not unicodedata.combining(char)).lower()
    return " ".join(plain.split())


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
    mcp_law_context.build_mcp_law_context = lambda **_kwargs: None
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


def test_employment_chat_export_renders_canonical_template_from_questionnaire(monkeypatch) -> None:
    from app.chat.models import Message, MessageRole, Session, SessionResult
    from app.chat.repository import InMemoryChatRepository

    chat_api = _load_chat_api()
    repository = InMemoryChatRepository()
    original_repository = chat_api._repository
    chat_api._repository = repository
    try:
        test_app = FastAPI()
        test_app.include_router(chat_api.router)
        client = TestClient(test_app)
        session = repository.create_session(Session(country="SK", discussion_type="advice", language="sk-SK"))
        questionnaire = """
1. Zamestnávateľ

Obchodné meno: Fiktíva Digital Solutions
Sídlo: Inovačná 18, 040 01 Košice
IČO: 99 999 999
DIČ: 2099999999
IČ DPH: SK2099999999
Zápis v registri: Obchodný register Mestského súdu Košice, oddiel: Sro, vložka č. 99999/V
Bankové spojenie: Testovacia banka, a. s.
IBAN: SK00 0000 0000 0000 0000 0000
Zastúpený: Ing. Martin Vzorový, konateľ
E-mail: personalne@fiktiva-example.sk
Telefón: +421 900 000 000

2. Zamestnanec

Meno a priezvisko: Lucia Vzorová
Rodné priezvisko: Testová
Dátum narodenia: 14. februára 1994
Rodné číslo: 945214/0000
Miesto narodenia: Poprad
Trvalý pobyt: Vzorová 27, 058 01 Poprad
Štátna príslušnosť: Slovenská republika
Číslo občianskeho preukazu: TEST000001
E-mail: lucia.vzorova@example.com
Telefón: +421 900 000 111
Bankový účet zamestnanca: SK00 1111 0000 0012 3456 7890

3. Údaje o pracovnom pomere

Číslo pracovnej zmluvy: PZ-2026-014
Druh pracovného pomeru: pracovný pomer na dobu neurčitú
Deň nástupu do práce: 1. októbra 2026
Skúšobná doba: 3 mesiace
Pracovná pozícia: AI vývojár / softvérový inžinier
Druh práce:
Návrh, vývoj, testovanie a údržba softvérových riešení využívajúcich umelú inteligenciu, integrácia AI modelov do informačných systémov, tvorba technickej dokumentácie a spolupráca na návrhu architektúry riešení.
Miesto výkonu práce:
Inovačná 18, 040 01 Košice, a práca na diaľku z územia Slovenskej republiky podľa dohody so zamestnávateľom.
Pravidelné pracovisko na účely cestovných náhrad: Košice
Nadriadený zamestnanec: Ing. Peter Modelový, vedúci vývoja

4. Pracovný čas

Týždenný pracovný čas: 40 hodín
Rozvrhnutie pracovného času: pondelok až piatok
Základný pracovný čas: od 9.00 do 15.00 hod.
Voliteľný pracovný čas: od 7.00 do 9.00 hod. a od 15.00 do 18.00 hod.
Prestávka na odpočinok a jedenie: 30 minút

5. Mzdové podmienky

Základná mesačná mzda: 3 200 EUR brutto
Variabilná zložka mzdy: do 10 % základnej mesačnej mzdy podľa dosiahnutých pracovných výsledkov
Výplatný termín: najneskôr 15. deň kalendárneho mesiaca nasledujúceho po mesiaci, za ktorý mzda patrí
Spôsob vyplácania mzdy: bezhotovostným prevodom na bankový účet zamestnanca
Mzdový stupeň: 4

6. Ďalšie pracovné podmienky

Dovolenka: v rozsahu podľa príslušných ustanovení Zákonníka práce
Výpovedná doba: podľa Zákonníka práce a dĺžky trvania pracovného pomeru
Home office: najviac 3 pracovné dni v týždni po dohode s nadriadeným
Pracovné vybavenie:
- služobný notebook
- mobilný telefón
- prístup k vývojovým a cloudovým nástrojom
- bezpečnostný autentifikačný token
Zamestnanecké benefity:
- príspevok na stravovanie podľa platných právnych predpisov
- príspevok na vzdelávanie do výšky 1 000 EUR ročne
- 3 dni pracovného voľna navyše
- flexibilný pracovný čas
- možnosť práce na diaľku

7. Podpisové údaje

Miesto uzatvorenia pracovnej zmluvy: Košice
Dátum uzatvorenia pracovnej zmluvy: 15. septembra 2026
Za zamestnávateľa:
Ing. Martin Vzorový
konateľ spoločnosti
Zamestnanec:
Lucia Vzorová
""".strip()
        repository.add_message(
            Message(
                session_id=session.id,
                role=MessageRole.USER,
                content=questionnaire,
            )
        )
        repository.add_message(
            Message(
                session_id=session.id,
                role=MessageRole.ASSISTANT,
                agent_name="LawyerSlovakia",
                content=(
                    "Pracovná zmluva je pripravená na export vo formáte PDF. "
                    "Pred podpisom ju skontrolujte s právnikom."
                ),
            )
        )
        repository.set_result(
            session.id,
            SessionResult(
                final_recommendation=(
                    "Pracovná zmluva je pripravená na export vo formáte PDF. "
                    "Pred podpisom ju skontrolujte s právnikom."
                ),
                judge_rationale="Direct lawyer reply prepared for session export.",
                metadata={},
            ),
        )

        options = client.get(f"/v1/chat/sessions/{session.id}/export/documents", headers=AUTH_HEADERS)
        assert options.status_code == 200
        assert options.json()["documents"] == [
            {
                "index": 0,
                "filename": "Pracovna_zmluva.pdf",
                "title": "Pracovna zmluva",
            }
        ]

        export_response = client.get(
            f"/v1/chat/sessions/{session.id}/export?format=pdf&kind=document",
            headers=AUTH_HEADERS,
        )
        assert export_response.status_code == 200
        assert export_response.headers["content-type"].startswith("application/pdf")
        assert export_response.content.startswith(b"%PDF")

        pdf_text = _pdf_text(export_response.content)
        canonical = _canonical_text(pdf_text)

        for expected in (
            "pracovna zmluva",
            "clanok i",
            "clanok iv",
            "clanok vii",
            "druh prace a jeho strucna charakteristika",
            "mzdove podmienky",
            "fiktiva digital solutions",
            "lucia vzorova",
            "ai vyvojar / softverovy inzinier",
            "3 200 eur brutto",
            "1. oktobra 2026",
            "v kosice, dna 15. septembra 2026",
            "za zamestnavatela",
            "jurisdigta",
            "skore overenia dokumentu: -",
        ):
            assert expected in canonical

        for unexpected in (
            "brutto brutto",
            "podmienky ich priznania a vyplatny termin",
            "generovany dokument podla diskusie",
            "zhrnutie pripadu",
            "session id:",
            "krajina:",
            "jazyk:",
            "podklady pre export",
            "odporucane kroky pred pouzitim",
            "case_update_json",
            "[mesto]",
            "[datum]",
            "prva odporucana doplnujuca otazka",
            "nevyriesene polia nahladu",
        ):
            assert unexpected not in canonical
    finally:
        chat_api._repository = original_repository
