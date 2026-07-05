from pathlib import Path
import tempfile
from datetime import datetime, timedelta, timezone

from aijurisdictionagents.agents.audio_action_tools import AIAudioToolRecognizerAgent
from aijurisdictionagents.api_db import ApiDatabaseStore, CASE_WRITE_WINDOW_EXPIRED_CODE
from aijurisdictionagents.api_db.e2e_test_users import provision_e2e_test_users

agent = AIAudioToolRecognizerAgent()
print("speechtype default => message (review STT transcript before send)")
for text in [
    "vytvor pripad splnomocnenie",
    "I want to validate company",
    "validate car vin WAUZZZ8K4DA123456",
]:
    result = agent.recognize(text)
    print(text, "=>", result)

print(
    "email_templates => non-OTP outbound emails use branded HTML with plain-text fallback; "
    "OTP/code emails remain plain text."
)
print(
    "subscription_invoice_checkout => checkout keeps subscriptions pending until payment confirmation; "
    "confirmation queues the invoice email with PDF and UBL XML attachments."
)
print(
    "mcp_auth_ux => browser MCP login/sign-up pages localize Slovak/English via Accept-Language; "
    "invalid OTP submissions re-render HTML warnings instead of JSON errors."
)
print(
    "mcp_auth_contract => getVersion/getStatistics are public; searchLaws/getLawText require "
    "a Bearer MCP token or x-mcp-api-key, and lowercase OAuth clients should use "
    "https://mcp.jurisdigta.eu/mcp."
)
print(
    "mcp_legal_source_search => MCP remains model-free; clients parse natural-language legal "
    "questions and call protected searchLegalSources with structured filters such as "
    "query='prenajom bytu', source_types=['laws','court_decisions'], published_year=2026, "
    "year_filter_mode='published_in'. Search defaults to metadata only; court-decision text "
    "requires getCourtDecision(full_version=True)."
)
print(
    "mcp_endpoint_claude_compat => /MCP remains accepted for Claude web and existing clients; "
    "it now advertises OAuth protected-resource metadata and requires the same per-user "
    "OAuth or MCP API key authentication for protected legal tools as /mcp."
)
print(
    "mcp_protocol_negotiation => initialize echoes supported client protocol versions "
    "2025-03-26, 2025-06-18, and 2025-11-25 for stricter MCP clients."
)
print(
    "mcp_oauth_redirects => hosted callbacks use explicit allowed hosts; local MCP clients keep "
    "http://localhost, http://127.0.0.1, and http://[::1] loopback redirect_uri support."
)
print(
    "mcp_wire_logging => MCP HTTP middleware logs redacted request/response envelopes; "
    "set MCP_WIRE_LOGGING_ENABLED=false to disable or MCP_WIRE_LOG_MAX_BYTES to adjust preview size."
)
print(
    "mcp_oauth_diagnostic_logs => OAuth metadata, authorize, token, refresh, and endpoint entry "
    "events log path/resource/audience context without passwords, OTPs, auth codes, PKCE verifiers, or tokens."
)
print(
    "mcp_oauth_claude_dcr => Claude/SmartIdentity-style dynamic client registration may include "
    "client_credentials, but JurisDigta normalizes public clients to authorization_code plus refresh_token "
    "and keeps the token endpoint closed to client_credentials."
)
print(
    "mcp_oauth_e2e_bypass => synthetic free/paid E2E users can skip MFA only for MCP OAuth when "
    "MCP_OAUTH_TEST_MFA_BYPASS_ENABLED, allowlisted emails, and a future expiry are configured."
)
print(
    "case_document_pdf_export => linked generated PDFs export the selected legal-document block only; "
    "assistant chatter, alternate-language blocks, and raw markdown stay out of the PDF."
)
print(
    "multilingual_document_exports => CASE_UPDATE_JSON case.documents entries are saved/exported "
    "as separate clean documents by default; use bundle=single_pdf only when one combined PDF is requested."
)
print(
    "unlimited_access_emails => "
    f"{sorted(ApiDatabaseStore.unlimited_access_email_allowlist())}"
)
print(
    "case_write_window_expired_error => "
    f"API 403 responses use code {CASE_WRITE_WINDOW_EXPIRED_CODE} with plan/day params "
    "so clients can localize the user-facing message."
)
with tempfile.TemporaryDirectory(prefix="jurisdigta-minimal-", ignore_cleanup_errors=True) as tmp:
    demo_root = Path(tmp)
    demo_store = ApiDatabaseStore(db_path=demo_root / "api.sqlite3", blob_root=demo_root / "blob")
    demo_store.initialize()
    demo_user = demo_store.create_user(
        email="minimal-routing@example.com",
        password="demo-secret",
        full_name="Minimal Routing Demo",
    )
    demo_case = demo_store.create_case(
        user_id=demo_user.user_id,
        company_id=None,
        title="Minimal citation demo",
    )
    demo_question_id = demo_store.add_case_message(
        case_id=demo_case.case_id,
        role="user",
        content="Which law supports this answer?",
        agent_name="User",
    )
    demo_answer_id = demo_store.add_case_message(
        case_id=demo_case.case_id,
        role="assistant",
        content="This answer is grounded in a tracked legal source.",
        agent_name="LawyerSlovakia",
    )
    demo_store.add_case_citation(
        case_id=demo_case.case_id,
        question_message_id=demo_question_id,
        answer_message_id=demo_answer_id,
        source_type="law",
        source_id="SK:ZZ:1992:460",
        source_url="/v1/laws/source?country_code=SK&collection_code=ZZ&law_year=1992&law_number=460",
        title="Constitution of the Slovak Republic",
        citation_label="460/1992 Zb. - Constitution of the Slovak Republic",
        law_number="460/1992 Zb.",
        effective_from="1992-10-01",
        snippet="Privacy-minimized citation metadata for review.",
        retrieval_tool="JurisDigta laws collector",
    )
    print(
        "case_citations => "
        f"{len(demo_store.list_case_citations(case_id=demo_case.case_id))} persisted citation"
    )
    free_route = demo_store.resolve_ai_model_route(
        user_id=demo_user.user_id,
        plan_code="free",
        task_type="chat_reply",
    )
    demo_store.upsert_ai_model_provider(
        provider_code="azure_foundry",
        provider_type="azurefoundry",
        display_name="Azure AI Foundry",
        base_url="https://example.openai.azure.com",
        api_version="2024-10-21",
        data_zone="eu",
        is_external=True,
    )
    case_route = demo_store.resolve_ai_model_route(
        user_id=demo_user.user_id,
        plan_code="case",
        task_type="chat_reply",
    )
    expired_subscription = demo_store.request_subscription_change(
        user_id=demo_user.user_id,
        plan_code="case",
    )
    paid_subscription = demo_store.update_subscription_status(
        subscription_id=expired_subscription.subscription_id,
        status="paid",
    )
    past_end = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat().replace("+00:00", "Z")
    with demo_store._connect() as conn:
        demo_store._execute(
            conn,
            "UPDATE user_subscriptions SET ends_at = ? WHERE subscription_id = ?",
            (past_end, paid_subscription.subscription_id),
        )
        conn.commit()
    expired_plan = demo_store.get_effective_subscription_plan(user_id=demo_user.user_id)
    expired_route = demo_store.resolve_ai_model_route(
        user_id=demo_user.user_id,
        plan_code=expired_plan.plan_code,
        task_type="chat_reply",
    )
    print(
        "model_routing_free => "
        f"{free_route.provider.provider_code}/{free_route.model_profile.model_code}"
    )
    print(
        "model_routing_case => "
        f"{case_route.provider.provider_code}/{case_route.model_profile.model_code}"
    )
    print(
        "model_routing_expired_paid => "
        f"{expired_plan.plan_code}/"
        f"{expired_route.provider.provider_code}/{expired_route.model_profile.model_code}"
    )
    print(
        "model_disclosure_label => "
        f"{expired_route.provider.display_name} - {expired_route.model_profile.model_code}"
    )
    e2e_users = provision_e2e_test_users(store=demo_store, password="demo-e2e-password")
    print(
        "e2e_test_users => "
        + ", ".join(f"{item.email}:{item.plan_code}" for item in e2e_users)
    )
    demo_store.upsert_ai_model_profile(
        model_profile_id="local_ollama_llama32",
        provider_id="local_ollama",
        model_code="llama3.2:3b",
        deployment_name="llama3.2:3b",
        billing_currency="EUR",
        eu_data_zone_capable=True,
        is_default_for_free=True,
        enabled=True,
    )
    demo_store.upsert_ai_task_route_policy(
        policy_id="default:free:default",
        task_type="default",
        plan_code="free",
        preferred_local_model_profile_id="local_ollama_llama32",
        allow_external=False,
        enabled=True,
    )
    demo_store.initialize()
    preserved_free_route = demo_store.resolve_ai_model_route(
        user_id=demo_user.user_id,
        plan_code="free",
        task_type="chat_reply",
    )
    print(
        "model_routing_admin_free_default => "
        f"{preserved_free_route.provider.provider_code}/"
        f"{preserved_free_route.model_profile.model_code}"
    )
print(
    "ai_model_admin => /app/admin/ai-models manages model providers, prices, "
    "groups, route policies, local free defaults, and audit events through "
    "server-authorized admin APIs."
)
print(
    "ai_model_user_assignment => /app/admin User model assignment searches by email, "
    "assigns any enabled local or external model profile as a per-user override, "
    "and disables the override with mandatory admin reason and audit logging."
)
print(
    "admin_case_reset => /app/admin can search users by email, list only case metadata, "
    "and soft-delete one selected case through /v1/admin/cases with mandatory reason "
    "and admin audit logging; public user delete stays write-window gated."
)
print(
    "ai_model_grafana_monitoring => JurisDigta Application Performance shows aggregate "
    "AI model status, request, token, and EUR cost panels without prompts, documents, "
    "emails, phone numbers, or legal-case facts in labels."
)
print(
    "laws_collector_grafana_monitoring => JurisDigta Laws Collector displays the "
    "latest imported law from the aggregate law label, for example 179/2026."
)
print(
    "service_healthchecks => HTTP services expose privacy-minimized /health; "
    "worker services report supervisor state, freshness, latest run result, "
    "and sanitized errors through protected operational status."
)
print(
    "court_decision_collector => imports Slovak court decisions into a separate "
    "PostgreSQL store with vectors, retry-hardened InfoSud requests, and "
    "pseudonymized MCP search output; run "
    "`python examples/court_decision_collector_minimal_demo.py` for the focused fixture demo."
)
print(
    "court_decision_grafana => JurisDigta Court Decision Service shows the aggregate "
    "latest imported court decision short name and published date without exposing "
    "court decision text, parties, file numbers, ECLI values, or source identifiers."
)
