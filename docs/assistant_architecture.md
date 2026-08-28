# Assistant Architecture

The internal JurisDigta assistant should use JurisDigta MCP as its source-of-truth tool layer for Slovak legal answers.

## Runtime Flow

1. The frontend starts or resumes a `/v1/chat` session.
2. The chat API records the user turn and gathers case history, uploaded documents, and processed document chunks.
3. For Slovak legal, jurisdiction, and legal-document-by-law turns, the chat API builds an internal MCP legal context over the configured MCP endpoint (`INTERNAL_MCP_BASE_URL` in production, with an in-process fallback for local tests) before any local or external model receives the prompt. Law-only and legal-document turns call `searchLaws` and focused `getLawText`; latest-law questions such as `Daj mi posledny zakon v systeme?`, `Zobraz mi poslednych 5 novych zakonov aj so sumarom coho sa tykaju.`, or `Daj mi sumar zo zakona 192/2026` call MCP before answer generation. Explicit latest-law counts are bounded to 10, and summaries come from public imported metadata. Court-decision turns call `searchLegalSources` with `source_types=["laws","court_decisions"]` so laws and case-law use the same governed tool surface.
4. For Slovak MCP status/statistics questions, including free-plan local Ollama routes, the chat API calls MCP `getVersion` and `getStatistics` before the model reply. The model receives only aggregate JSON from those tools and formats it for the user; it must not invent version, imported-law count, or jurisdiction values not present in the JSON.
5. When a Slovak legal turn needs case-law support, the chat API or MCP client may call `searchCourtDecisions` and `getCourtDecision`. Court-decision context must default to metadata or pseudonymized public text for UI and external model routes.
6. The lawyer model receives the user conversation, case documents, uploaded documents, internal MCP law context, optional court-decision context, and optional aggregate MCP status JSON.
7. Every MCP legal-source processing event includes a user-visible proof notice localized by session language: Slovak `JurisDigta MCP server bol kontaktovaný na získanie najnovších právnych informácií.`, German `Der JurisDigta MCP-Server wurde kontaktiert, um aktuelle Rechtsinformationen abzurufen.`, and English `JurisDigta MCP Server was contacted to retrieve the latest legal information.` Frontend and mobile clients display the backend processing message rather than inventing their own source-trust wording.
8. The model must cite MCP law identifiers and relevant sections when the MCP context contains them, and must say when current-law lookup was unavailable or inconclusive. Court decisions must be cited as case-law support with court, date, ECLI or file number when available, not as binding statutory text.
9. On the first user turn of a new chat/case, the chat API now runs `AICaseTypeDetectionAgent` before the main lawyer prompt is built. The detector ranks admin-managed `case_types`, applies a conservative confidence-threshold rule, persists the selected `case_type`, prompt ids, and template ids on both the session and the case, and records privacy-minimized detection events for later audit/export.
10. If detection is ambiguous, the assistant asks one clarification question instead of forcing a legal workflow. If the detected case type has no linked prompt and no linked template, the system fails closed for drafting and tells the user the draft cannot be prepared safely yet. If only one of prompt/template is missing, the system logs an admin-visible catalog gap and continues with the available catalog guidance only.
11. Document drafting remains a separate validated workflow: ask for missing facts, require explicit user confirmation before final drafting, then export generated assets through the document export endpoints.

## Case Citations

Chat result metadata now normalizes JurisDigta law lookup results into durable case citations. The API stores only citation metadata and bounded snippets, linked to the case, the latest user case communication, and the assistant case communication. It does not duplicate full law text, court-decision bodies, prompts, or personal data in the citation table.

`POST /v1/chat/sessions/{session_id}/reply` returns assistant messages with `citations[]` when structured legal sources are available. `GET /v1/cases/{case_id}/history` returns the same answer-level `citations[]` on each assistant/system history message plus a case-level aggregate list. `GET /v1/cases/{case_id}/citations` returns the authorized aggregate list for the active case citation panel.

The frontend renders per-answer citations below assistant answers and a deduplicated case citation list in the right configuration panel. Empty states stay explicit when no reliable citation exists or lookup was inconclusive.

PostgreSQL-backed MCP law queries configure their transaction-local statement timeout with parameterized `set_config`. PostgreSQL does not accept a bound placeholder in `SET LOCAL statement_timeout`, so using `set_config` keeps the timeout value parameter-safe and prevents law retrieval from failing before citation metadata can be persisted. The focused API regression test protects this database-session contract.

The Playwright scenario `frontend/aijurisdictionfronend/e2e/issue-608-mcp-case-citations.spec.ts` starts from a case with no citations, completes a synthetic MCP-grounded legal answer, and verifies that the same structured source is visible below the answer and in the case citation panel. Its privacy-reviewed final-state screenshot is retained under `docs/screenshots/issue-608/`.

For generated legal-document drafts, the live assistant stream and the hydrated case-history path must converge on the same user-visible output. If the stream finishes with a progress sentence but the refreshed case history contains a formatted document preview or generated-document action, the frontend shows the hydrated preview/action immediately and keeps the same preview/action after reload. This prevents users from seeing terminal PDF-progress text when the generated document is already persisted.

Legal-source citations carry retrieval provenance. JurisDigta MCP/vector results use source score `1.0` and retrieval tools such as `JurisDigta MCP searchLaws` or `JurisDigta MCP searchCourtDecisions`. If the system vector DB has no reliable legal source, `AIWebSearchAgent` legal fallback remains blocked until explicit user approval exists for the external web-search scope. Approved fallback citations use source score `0.9`, `source_type=web`, and must render a visible warning that the source came from official web search rather than the JurisDigta system vector DB.

## Quality Target

Claude-like quality here means the assistant is not answering from model memory alone. It must ground Slovak legal answers in current JurisDigta MCP data, preserve case context, use uploaded documents when available, and produce downloadable documents only after the user confirms the drafting step.

Court-decision retrieval is high-compliance-risk data processing because decisions can contain personal data. External providers and UI snippets receive pseudonymized decision text by default. Raw court-decision context is reserved for controlled internal/local model routes and must not be copied into logs, telemetry, screenshots, or external prompts.

## Local Models

Local models are acceptable for free-plan traffic, low-risk support tasks such as routing, summarization, anonymization, first-draft generation, and offline demos. Production legal answers may use local models only when the configured route policy allows it and the local model has passed the same law-citation and document-quality evaluations as the paid production model.

For production on `jurisdigta-server`, local models should run behind a separate local model service. The default local runtime is Ollama bound to localhost, for example `http://127.0.0.1:11434`, with models managed by Ollama CLI commands such as `ollama pull`, `ollama list`, `ollama ps`, and `ollama rm`.

The chat API resolves provider, model, deployment, and credentials through the API database model-routing tables. Free/default traffic is seeded to `local_ollama_default` with exact model `qwen3:1.7b`; paid case traffic is seeded to the EU-capable Azure Foundry `gpt-4o-mini` route. `LLM_PROVIDER`, `LOCAL_LLM_*`, `OPENAI_MODEL`, and `AZURE_OPENAI_DEPLOYMENT` are not chat-routing configuration sources. If a selected database route is incomplete, the API must fail closed and report the missing provider/profile/credential setup instead of silently switching providers. Direct free-plan local replies use a compact GDPR/EU AI Act guardrail prompt and capped local output so the CPU-only Ollama route can answer inside public edge timeouts without sending free-plan user content to an external provider.

Provider and model-profile records also contain validated, non-secret `model_parameters`. Provider values are defaults; profile values override them. A profile can set a key to JSON `null` to remove an inherited provider default. For example, an Azure provider may default to `{"temperature": 0.2}` while its `gpt-5-mini` profile uses `{"temperature": null}` so the request omits `temperature` and the model applies its supported default. Routing never guesses compatibility from a model name and never retries by silently discarding an explicitly configured parameter. The allowlist accepts only bounded chat-generation scalars; credentials, endpoints, prompts, case data, arbitrary SDK kwargs, and nested objects are rejected.

The resolved Azure/OpenAI request is built dynamically. Missing or explicitly removed parameters are not sent to the SDK. Operational logs and admin audit events record only applied parameter names, provider/profile identity, and validation/provider error metadata; they do not record parameter values, prompts, documents, credentials, or case content.

Local generation has a 600-second default deadline configured by `LOCAL_LLM_REQUEST_TIMEOUT_SECONDS`. During a slow request, the SSE stream emits a localized replaceable progress event every `LOCAL_LLM_REQUEST_VISIBLE_PROGRESS` seconds (15 by default). Local and external provider timeouts use distinct typed errors and privacy-safe `ai_model_processing_timeout` operational events; timeout handling never logs prompt/document content or silently changes providers.

The compact free-plan prompt does not bypass MCP grounding. If a free-plan local Ollama turn asks about Slovak law, jurisdiction, court decisions, or legal documents that must be created under law, the API retrieves bounded JurisDigta MCP context first and then passes that context to Ollama for drafting or formatting.

The compact free-plan prompt still accepts aggregate JurisDigta MCP status context for MCP version/statistics questions. That context is limited to `getVersion` and `getStatistics` JSON, contains no user identifiers or raw legal text, and is supplied to Ollama only for Slovak presentation formatting.

Local Ollama chat routes use Ollama's native `/api/chat` endpoint with `think: false`, `stream: false`, and a bounded `num_predict` value. This avoids Qwen reasoning models returning an OpenAI-compatible response with empty `message.content` and reasoning-only metadata, which would otherwise look like a missing assistant answer in the web app.

Language selection is enforced at the orchestration prompt layer for local and external routes. When the requested language is `sk-SK`, all visible assistant content, including notes, summaries, questions, labels, and any reasoning explanation, must stay in Slovak. Local Ollama prompts explicitly reject English meta-analysis such as "We need to..." and hidden chain-of-thought text because smaller reasoning models can otherwise emit English analysis as normal answer content.

The API must not load large local model files directly inside the FastAPI process for normal production traffic. Loading a 10 GB to 30 GB model inside API workers increases startup time, RAM/VRAM pressure, deployment risk, and failure blast radius. The API should stay lightweight and call the local model service through the model router, while Ollama owns model download, storage, loading, unloading, health checks, and runtime isolation.

Direct model paths are reserved for a future dedicated worker/runtime adapter, not the default API process.

## Model Token Accounting

Provider prices such as `$30 / 1M output tokens` mean one million tokens generated by the model. Output tokens are the assistant text the model returns: legal answers, document clauses, extracted summaries, structured JSON, or the textual content later rendered into DOCX/PDF. PDF rendering itself is not charged as model output unless the model is asked to generate more text or layout instructions for that render.

For rough planning, 1,000 output tokens is usually about 500 to 800 words depending on language and formatting. A short one-page answer may be around 500 to 1,500 output tokens. A multi-page legal document can be several thousand output tokens. The exact count must come from provider-reported usage when available, with tokenizer-based estimates only as fallback.

The model router and usage ledger must track input, cached input, output, and total tokens for each model request. For paid cases, these counts must aggregate by user, subscription, case, task type, provider, model, and time window so JurisDigta can enforce budgets and show Grafana spend/usage panels without exposing legal facts or document contents. Route policies can set `max_cost_eur`; once the recorded user/plan/task cost reaches that cap, the API resolver falls back to the configured local model with route type `local_budget_fallback` when `fallback_local_on_budget` is enabled, otherwise it fails closed with `budget_exhausted`.

For case audit and EU AI Act traceability, each chat model-use row also links to the case session, the user question message, and the assistant answer message. The ledger stores only a bounded question preview and SHA-256 hash; authorized reviewers can use `/v1/cases/{case_id}/ai-model-audit` together with case history when they need to verify exactly which model answered which question.

Case export now also includes `case-catalog-detection.json`, which contains the persisted case/session catalog selections and the detection-event trail. This makes it possible to trace which catalog entry was auto-selected, what confidence rule was applied, and whether prompt/template coverage gaps blocked or degraded the drafting workflow.
