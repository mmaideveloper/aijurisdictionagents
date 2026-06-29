from pathlib import Path
import tempfile
from datetime import UTC, datetime, timedelta

from aijurisdictionagents.agents.audio_action_tools import AIAudioToolRecognizerAgent
from aijurisdictionagents.api_db import ApiDatabaseStore, CASE_WRITE_WINDOW_EXPIRED_CODE

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
    "mcp_wire_logging => MCP HTTP middleware logs redacted request/response envelopes; "
    "set MCP_WIRE_LOGGING_ENABLED=false to disable or MCP_WIRE_LOG_MAX_BYTES to adjust preview size."
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
    past_end = (datetime.now(UTC) - timedelta(days=1)).isoformat().replace("+00:00", "Z")
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
print(
    "ai_model_admin => /app/admin/ai-models manages model providers, prices, "
    "groups, route policies, and audit events through server-authorized admin APIs."
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
    "service_healthchecks => HTTP services expose privacy-minimized /health; "
    "worker services report supervisor state, freshness, latest run result, "
    "and sanitized errors through protected operational status."
)
