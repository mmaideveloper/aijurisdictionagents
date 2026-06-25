from aijurisdictionagents.agents.audio_action_tools import AIAudioToolRecognizerAgent
from aijurisdictionagents.api_db import ApiDatabaseStore

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
    "service_healthchecks => HTTP services expose privacy-minimized /health; "
    "worker services report supervisor state, freshness, latest run result, "
    "and sanitized errors through protected operational status."
)
