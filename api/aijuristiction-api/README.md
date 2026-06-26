# aijuristiction-api

## Testing

Run the API unit tests from the repo-managed Python environment:

```powershell
..\..\.conda\python.exe -m pytest tests
```

Run the local API lint/type-check gate before committing API changes:

```powershell
..\..\scripts\validate_api.ps1
```

`mypy app` is intentionally scoped to the API package. Shared repository modules imported through
`aijurisdictionagents` and `services` are treated as external dependencies for this gate so unrelated
type debt outside `api/aijuristiction-api` does not block API CI.

Dedicated API service project for exposing `aijurisdictionagents` to frontend clients.

## Registration email verification flow

Mobile/API registration now supports email one-time-code verification:

- `POST /v1/users/sign-up/send-code` sends a one-time code to the requested email.
- `POST /v1/users/sign-up/complete` finishes account creation only when the code is valid.
- Successful account creation still queues the welcome email notification.
- Registration and device sign-in OTP codes now expire after 30 minutes.

Device-bound login flow:

- `POST /v1/users/sign-in/send-code` sends a login OTP to the account email for the provided phone+device.
- `POST /v1/users/sign-in/verify-code` validates OTP and returns a device-bound auth token.
- `POST /v1/users/sign-in/device` allows silent sign-in on the same device by reusing the device-bound token.

## Azure infrastructure

Use the root `infra/` folder to provision Azure resources and deploy from local machine:

```powershell
.\infra\scripts\deploy_api.ps1 -SubscriptionId "<your-subscription-id>" -AcrName "<globally-unique-acr-name>"
```

See `infra/README.md` for full setup.

For Azure/PostgreSQL schema upgrades, SQL migrations in `databases/api/migrations/` own PostgreSQL-only tables such as `permanent_memory`. The runtime `ApiDatabaseStore.initialize()` path now keeps SQLite-only bootstrap SQL out of the PostgreSQL deployment path.

## Run locally (Conda)

From the repository root:

```bash
conda env create -f environment.yml -p ./.conda
conda activate ./.conda
cd api/aijuristiction-api
pip install -e ".[dev]"
uvicorn app.main:app --reload --port 8080
```

If the `.conda` environment already exists, skip `conda env create`.

### Console logging

- API now writes request logs to console by default (method, path, status, duration, request id, correlation id, origin, user agent).
- On startup, API prints `API Starting` with API/core version and active log level.
- API chat provider/model selection is resolved from the database model-routing tables. `LLM_PROVIDER` is only honored when explicitly set to `mock` for deterministic offline tests.
- Set log level with `API_LOG_LEVEL` (fallback: `LOG_LEVEL`), for example:

```bash
API_LOG_LEVEL=DEBUG uvicorn app.main:app --reload --port 8080
```

Required setup for chat model routing:

- Free/default users use the seeded `local_ollama_default` route: provider `local_ollama`, base URL `http://127.0.0.1:11434/v1`, exact model `qwen3.6:27b`.
- Paid `case`, `basic`, `premium`, and `unlimited` users use the seeded Azure Foundry route `azure_foundry_gpt_4o_mini`: exact model/deployment `gpt-4o-mini`.
- Azure Foundry chat endpoint belongs in `ai_model_providers.base_url`.
- Azure Foundry API key or token belongs in encrypted `ai_model_credentials`, managed through `/v1/admin/ai-models`.
- Set `AI_MODEL_CREDENTIAL_ENCRYPTION_KEY` and `JURISDIGTA_ADMIN_EMAILS` in deployed environments.

Shared embedding selection:

- `SYSTEM_EMBEDDING_MODEL_OPTION=local|cloud`
- `SYSTEM_EMBEDDING_MODEL=all-MiniLM-L6-v2` for the local sentence-transformer path
- local model files are cached under the repo `aimodels/` directory
- deployed Azure environments should keep `SYSTEM_EMBEDDING_MODEL_OPTION=cloud`

Embedding env vars:

- `OPENAI_KEY`
- `OPENAI_EMBEDDINGS_MODEL` (recommended: `text-embedding-3-large`)
- `AZURE_OPENAI_ENDPOINT`
- `AZURE_OPENAI_EMBEDDINGS_MODEL` (embedding deployment name, recommended: `text-embedding-3-large`)
- one of: `AZURE_OPENAI_API_KEY` or `AZURE_OPENAI_AD_TOKEN` when cloud embeddings are enabled

Local API startup loads the repository root `.env` automatically. If you override variables in the shell before starting `uvicorn`, those explicit shell values still win because `.env` is loaded with `override=False`.

AI model admin management and routing API:

- `GET /v1/admin/ai-models` returns providers, model price profiles, route policies, user groups, group memberships, users eligible for assignment, and recent admin audit events.
- `POST /v1/admin/ai-models/providers`, `/profiles`, `/groups`, `/groups/{model_group_id}/members`, and `/policies` update routine model-router settings without editing environment files.
- `GET /v1/admin/ai-models/providers`
- `PUT /v1/admin/ai-models/providers/{provider_id}`
- `GET /v1/admin/ai-models/profiles`
- `PUT /v1/admin/ai-models/profiles/{model_profile_id}`
- `GET /v1/admin/ai-models/credentials?reveal=false`
- `PUT /v1/admin/ai-models/providers/{provider_id}/credentials`
- `PATCH /v1/admin/ai-models/credentials/{credential_id}`
- `GET /v1/admin/users`
- `PATCH /v1/admin/users/{user_id}`

Production authorization uses the Cloudflare Access `cf-access-authenticated-user-email` header with either a database `role=admin` user or the `JURISDIGTA_ADMIN_EMAILS` fallback allowlist. Local loopback development may send `x-jurisdigta-admin-user-id`. The credential endpoints also require API authentication and reserve `reveal=true` for authorized admin maintenance.
- Admin responses never return provider secrets or legal case content. External provider changes are audited with actor, entity, old/new summaries, reason, and correlation id.

Document processing mode:

- `DOCUMENT_PROCESSOR_OPTION=api`: uploaded case documents are processed immediately inside the API and stored with extracted text plus vector data.
- `DOCUMENT_PROCESSOR_OPTION=local`: legacy alias for `api`.
- `DOCUMENT_PROCESSOR_OPTION=azure`: uploads stay pending until the Azure Container Apps document-processor job runs.
- Default and recommended value: `DOCUMENT_PROCESSOR_OPTION=api`

### Policy-driven multi-intent document task planning

The chat reply path now uses a single legal agent with a reusable policy layer for uploaded-document intents. Each matched policy contributes ordered tasks and communication rules before the legal agent is prompted.

Implementation note: the policy logic now lives in a dedicated chat service module so `app/chat/api.py` can stay focused on endpoint mapping and request/response handling.

Examples:

- `Fix uploaded document based on current law and send me summary from document`
- `Analyze uploaded agreement, rebuild outdated clauses, and summarize the result`

When the same message asks for multiple document actions, the API keeps the user's intent order and instructs the model to execute the tasks in sequence, for example:

1. review uploaded document
2. update/rebuild if current law requires it
3. prepare summary

Current built-in policies:

- `document_analysis`
- `document_modernization`
- `document_summary`

The summary step is instructed to describe the updated result when both update + summary are requested together. Future policies can add their own tasks/guidance while still using the same single-agent flow.

If summary-like output is requested before uploaded documents are processed, the policy note tells the agent to defer content-specific summary output until processed documents are available.

Minimal runnable example:

```bash
python examples/document_task_plan_demo.py
```

### Tool-first Slovak company drafting

For Slovak company-document workflows, the API now uses a hybrid model-driven tool orchestration:

- backend performs deterministic intent/tool routing and executes available registry tools first,
- verified tool output is injected into LLM prompt context,
- LLM prepares the final user-facing answer (or clarification question when data conflicts are detected).

Country-specific intake and tool-first shortcuts now live under `app/chat/country_services/`. The API endpoint layer dispatches by `session.country`, so new countries can add their own country module without expanding `app/chat/api.py` with more country-specific phrase matching.

Current behavior for `s.r.o.` / `a.s.` drafting flows:

- if the user provides a Slovak company name or IČO, the API first runs `obchodny_register_company_check`
- the ORSR lookup now enriches the top company match through the detail endpoint `/api/legal-person/extract-full`, so the API can also see current stakeholders, statutory representatives, company-signing rules, deposit values, and normalized status (`Aktívna` vs. `v likvidácii`)
- the assistant then uses verified company name, IČO, seat, and status instead of asking for those facts again
- if the register shows exactly one current stakeholder, the API can reuse that stakeholder as the likely transferor instead of asking for the transferor again
- if the requested main document usually requires related resolutions, updated articles, or registry attachments, the assistant explicitly offers to prepare that fuller package too
- if the user later says `áno` / `show me the draft`, the API returns the working draft directly instead of looping back into the same intake questions
- questions asking for the available Slovak verification tools, including noisy STT forms such as `zoznam tulsov`, are answered deterministically from the registered tool definitions before the API initializes the LLM client; this avoids Azure retries for simple capability/help turns
- Slovak payment-confirmation requests that already contain a final PDF command, amount, company, due date, and vehicle SPZ now take a deterministic tool-first path: ORSR is checked first, consented address/car validation progress is emitted, and the assistant returns only a short document-ready message while the PDF export uses the captured facts.
- Local Azure Foundry LLM calls use the operating-system certificate trust store, which avoids Windows corporate/root CA failures such as `SSL: CERTIFICATE_VERIFY_FAILED` during mobile voice tests.
- short confirmation replies now pass through Slovak/mojibake-safe normalization, so `áno`, `ano`, and common corrupted STT/log forms like `�no` confirm an unanswered PDF-generation prompt instead of causing the assistant to ask the same question again
- when a document is already ready and the user sends only a short confirmation such as `áno`, the API returns the ready/export status directly without calling the LLM for another intake turn
- for direct register-information questions like `kto je majiteľ firmy ...`, the API now returns ORSR-backed owner/statutory summary directly (without falling back to stale share-transfer prompts from earlier turns in the same session)
- repeated ORSR lookups for the same company query are now reused from in-memory API cache during the conversation, so follow-up turns do not keep revalidating identical company data
- short follow-up replies such as `ano`, `50%`, or `nie` now keep the Slovak share-transfer workflow active when an earlier turn already established the company context
- first-turn share-transfer facts like `50%` and `konatel / sposob konania sa nemenia` are now treated as settled inputs, so the model does not re-ask them unless the user later contradicts them
- direct document-generation replies are now instructed to say the draft/package is ready for export instead of falsely claiming that PDF/ZIP files were already created or attached
- `GET /v1/chat/sessions/{session_id}/export?format=pdf&kind=document` now returns a ZIP package when `CASE_UPDATE_JSON.case.documents` lists multiple generated documents; single-document exports still return one PDF
- when the user-provided transferor differs from the ORSR owner, the backend now stops drafting and asks a direct confirmation question comparing ORSR vs user-provided owner data instead of treating it as a generic missing-input follow-up
- when a request indicates an additional/new owner, the model is now instructed to proactively recommend related Slovak company-document and filing changes too, including whether the updated `spolocenska zmluva` / `zakladatelska listina` and ORSR attachment package are needed
- Slovak share-transfer PDF export now rebuilds the document package from ORSR-enriched company data, so exported drafts keep verified company name / seat / ICO and include the main package sections instead of falling back to a generic single-document template
- generic transferor phrases such as `vlastnik firmy` are now normalized to the verified ORSR owner when the register shows exactly one current stakeholder
- the Slovak share-transfer conflict-resolution helper now returns an explicit typed structure, which keeps the GitHub API build green under `mypy` for the zip-document export flow
- if user-provided transferor identity conflicts with ORSR stakeholders, the LLM prompt now enforces a confirmation step before final document generation.
- when the user resolves that transferor conflict with a short reply like `podla ORSR`, the backend now locks in the verified ORSR owner and keeps verified company identity data such as `IČO` as settled instead of asking for them again
- once the user resolves the ORSR-vs-user transferor conflict, that choice now persists into later follow-up turns such as `ano`, so the API continues to draft the requested package instead of reopening the same transferor conflict
- if the model returns the case payload inside a fenced ```json block instead of the required `CASE_UPDATE_JSON:` marker, the API now still extracts that payload, ignores question marks inside the machine JSON when deciding whether to wait for another reply, and keeps export/download working
- user-facing chat text is now sanitized to remove technical persistence preambles like `Tu je JSON pre uchovanie prípadu`, internal saved-document notices such as `/v1/cases/.../documents/...`, and fake relative file links like `documents/...pdf`; the user sees only the natural-language answer while the backend still keeps the machine payload for export/state handling
- if a multi-document Slovak share-transfer draft is present in the visible assistant text but the model forgot to populate `CASE_UPDATE_JSON.case.documents`, the export endpoint now falls back to the detected document sections and still returns a ZIP package with one PDF per detected document instead of collapsing everything into a single `final-document.pdf`
- the same visible-section ZIP fallback now applies to Slovak rental packages (for example `Nájomná zmluva`, `Inventárny zoznam`, `Potvrdenie o prevzatí bytu`) even when machine case-update JSON is missing, so sectioned package exports stay downloadable as ZIP
- the fallback ZIP detector now ignores ordinary single-document section headings such as `Zmluvne strany` or `Doba najmu`, so sectioned contracts continue to export as one PDF instead of being split into a fake ZIP package
- if a document-generation turn ends with a generic wait message such as `Prosim, dajte mi chvilu.`, the API now replaces that placeholder with an explicit document-package-ready completion message before persisting the final assistant turn
- completed `ReadUser` sessions now also accept follow-up status questions such as `stav dokumentov` and answer from the saved export/result state instead of failing with `Session already completed`
- in `POST /v1/chat/sessions/{session_id}/stream` with `user_simulation_mode=ReadUser`, tool lifecycle progress is streamed live as `processing` SSE events:
  - immediately when backend receives user turn: localized processing status (`Processing...`, `Spracovavam...`, `Verarbeite Anfrage...`, ...)
  - immediately after each user message: localized thinking status (`Thinking...`, `Premyslam...`, `Ich denke nach...`, ... depending on country/language)
  - before ORSR lookup: localized ORSR start message (for example `Idem overit spolocnost '<name>' v ORSR.`, `Ich werde das Unternehmen '<name>' im ORSR pruefen.`, `I am going to verify company '<name>' in ORSR.`)
  - when ORSR data is reused from cache: localized cache-hit progress message so clients can keep showing that the backend is still processing
  - when the assistant prepares a multi-document package in `ReadUser` stream mode, the backend now emits one progress event per prepared document name before the final assistant message instead of waiting to describe the whole package at once
  - after the result/export is actually ready, the backend emits a final document-package-ready processing event so clients can show a definitive completion state instead of ending on a generic `please wait` sentence
  - after ORSR lookup: localized ORSR completion message (for example `Overenie spolocnosti v ORSR je hotove: ...`, `Unternehmenspruefung im ORSR abgeschlossen: ...`, `Verification of company done in ORSR: ...`)
  This lets clients show small progress updates while waiting for the final assistant answer.
- stream workers now log unexpected failures server-side with session id and exception type before sending the SSE `error` event. The log intentionally avoids raw transcript content so operational debugging stays compatible with the repository GDPR/data-minimization baseline.

Minimal runnable example:

```bash
python examples/api_tool_capabilities_demo.py
python examples/share_transfer_related_documents_demo.py
python examples/share_transfer_tool_first_demo.py
python examples/api_tool_progress_stream_demo.py
```

Full draft package example:

```bash
python examples/share_transfer_tool_first_demo.py
```

Local embedding similarity demo:

```bash
python examples/local_embedding_semantic_search_demo.py
```

When using API key auth, leave `AZURE_OPENAI_AD_TOKEN` unset instead of setting it to an empty string. Likewise, leave `AZURE_OPENAI_API_KEY` unset when using Entra ID auth. The shared Azure Foundry loader strips blank auth values, but direct SDK smoke scripts can fail with an invalid `Authorization: Bearer ` header when an empty token variable is present.

Optional explicit override:

```bash
LLM_PROVIDER=mock uvicorn app.main:app --reload --port 8080
```

## Run with Docker

```bash
cd api/aijuristiction-api
docker compose up --build
```

This local Docker stack now runs:

- PostgreSQL 16 with `pgvector`
- API container built from the repository root so it includes `src/aijurisdictionagents`, migrations, and scripts
- Dedicated MCP container on port `8070`, started from `app.mcp_main:app`
- Browser-based MCP login, sign-up, and OAuth authorization pages localize user-facing copy from
  `Accept-Language` (`sk` for Slovak browsers, English fallback). Invalid OTP submissions re-render
  the same HTML form with an accessible warning instead of returning a JSON error body, while keeping
  OTP values out of logs and response state.

Useful overrides:

```bash
API_PORT=8081 MCP_PORT=8070 LLM_PROVIDER=mock docker compose up --build
```

The compose file stores database files under the shared repository `databases/` folder and points the API at:

- `DB_OPTION=postgres`
- `DB_CLOUD=postgresql://postgres:postgres@postgres:5432/aijurisdiction`
- `STORAGE_OPTION=local`

Do not run this stack at the same time as the standalone `start-postgres` API instance because both use the same PostgreSQL data directory.
That shared database directory is now `runs/storage/api/postgres/data`.
If you still have legacy local data under earlier local PostgreSQL paths, the managed PostgreSQL startup path migrates it into `runs/storage/api/postgres`.

If you want only the database container or the repository database rules, use `docs/DATABASE_LAYOUT.md`.

## Endpoints scaffolded

- `GET /`
- `GET /health`
- `GET /version`
- `GET /v1/observability/logs`
- `POST /v1/users/sign-up`
- `POST /v1/users/sign-in`
- `POST /v1/users/sign-in/phone`
- `PATCH /v1/users/{user_id}`

`GET /health` verifies the configured API database connection before returning healthy.
Healthy responses include `status=ok`, `service=aijuristiction-api`,
`llm.status`, and `database.status`. Database failures return HTTP 503 with
`error=database_unavailable` and a sanitized message that does not echo
connection strings, credentials, raw exception text, prompts, documents, email
addresses, or generated legal output.

See `docs/SERVICE_HEALTHCHECKS.md` for the reusable health-check rule across
HTTP services and background workers.
If the database is unreachable or misconfigured, the endpoint returns `503` with
`error=database_unavailable` and a `message` field that the mobile app can show directly.
The response reports `provider=model_routing` for normal chat routing and `provider=mock`
only when deterministic offline testing was explicitly requested.

Minimal runnable example:

```bash
curl -fsS http://127.0.0.1:8080/health
```

Example healthy response:

```json
{
  "status": "ok",
  "llm": {
    "status": "ok",
    "provider": "mock"
  },
  "database": {
    "status": "ok",
    "backend": "local"
  }
}
```

`GET /` renders a lightweight HTML status page that shows the same public metadata
returned by `GET /version`. The page links back to `/version` for clients that need
the raw JSON response.

Minimal runnable example:

```bash
python examples/api_root_version_page_minimal_demo.py
```

`GET /version` response includes:
- `api_version`: API package version (`api/aijuristiction-api/pyproject.toml`).
- `core_version`: core system version from installed `aijurisdictionagents` package or local `src/aijurisdictionagents/__init__.py` during monorepo development.
- `last_law_update_date`: latest law-ingestion timestamp available to the system from the laws database. This reflects the newest law content collected by the law processor, even when the underlying LLM was trained earlier.
- `last_law_update_source`: whether that timestamp comes from country-specific or global `law_documents` data.
- `last_collector_run_at`: latest sequential laws collector run timestamp from `collector_progress`, including country/source-system suffix when available.
- `last_processed_law`: latest successfully processed law identifier in `number/year` format, for example `234/2026`.
- `model_knowledge_cutoff_date`: LLM cutoff date resolved from the current model metadata and cached in `permanent_memory`.
- `model_knowledge_cutoff_source`: source URL used for the resolved cutoff date, typically an official OpenAI model page.
- `law_reference_links`: recent official law links available in the system knowledge store.
- `law_citations`: structured version-specific legal citations resolved from the current answer/session context. Each item includes the law identifier, title, version token, effective date, and an `open_url` that can stream the stored full-law source from local storage or Azure Blob.
- `mobile_app_version`: latest mobile app version from `mobile_app/pubspec.yaml`.
- `mobile_app_release_url`: release page used by the mobile app update flow.
- `mobile_app_apk_download_url`: default APK asset URL used by Android in-app update flow.
- `laws_by_country`: country-specific law metadata map keyed by lowercase ISO country code. Today it contains `sk`.

Additionally, the API persists `permanent_memory.key=llm_model_setup` with
`llm_modelname`, `cutoff_date`, and `cutoff_source`. When no cached value exists,
the API uses `AIWebSearchAgent` to find an official OpenAI model page, extracts the
knowledge cutoff, and stores it for reuse. If search returns no hits, it falls back
to a direct official model-page lookup under `https://platform.openai.com/docs/models/<model>`.
For Azure deployments that use custom deployment aliases, the resolver also matches
known official model slugs embedded in the deployment name, for example
`juris-gpt-4o-mini-dev -> gpt-4o-mini`.

Example:

```json
{
  "service": "aijuristiction-api",
  "version": "1.0.260321",
  "api_version": "1.0.260321",
  "core_version": "0.1.0",
  "last_law_update_date": "2026-03-20T00:00:00Z",
  "last_law_update_source": "law_documents_global",
  "last_collector_run_at": "2026-03-30T12:30:00Z (SK:slovlex)",
  "last_processed_law": "234/2026",
  "model_knowledge_cutoff_date": "2023-10-01",
  "model_knowledge_cutoff_source": "https://platform.openai.com/docs/models/gpt-4o-mini",
  "law_reference_links": [
    "https://www.slov-lex.sk/pravne-predpisy/SK/ZZ/2026/10/"
  ],
  "laws_by_country": {
    "sk": {
      "country_code": "SK",
      "last_law_update_date": "2026-03-21T00:00:00Z",
      "last_law_update_source": "law_documents_country",
      "last_collector_run_at": "2026-03-30T12:30:00Z (SK:slovlex)",
      "last_processed_law": "234/2026",
      "model_knowledge_cutoff_date": "2023-10-01",
      "model_knowledge_cutoff_source": "https://platform.openai.com/docs/models/gpt-4o-mini",
      "law_reference_links": [
        "https://www.slov-lex.sk/pravne-predpisy/SK/ZZ/2026/10/"
      ]
    }
  },
  "mobile_app_version": "0.1.5+18",
  "mobile_app_release_url": "https://github.com/mmaideveloper/aijurisdictionagents/releases/latest",
  "mobile_app_apk_download_url": "https://github.com/mmaideveloper/aijurisdictionagents/releases/latest/download/app-release.apk"
}
```

Country payload demo:

```bash
python examples/version_country_payload_demo.py
```

`GET /v1/observability/logs` returns recent Azure Application Insights / Log Analytics records for the deployed API and Azure workers.

Query params:

- `minutes`: lookback window in minutes, default `60`
- `limit`: max records to return, default `100`
- `application`: optional `api`, `document_processor`, or `laws_collector`
- `level`: optional `debug`, `info`, `warning`, `error`, or `critical`
- `source`: optional `trace`, `exception`, or `request`

Example:

```bash
curl "http://localhost:8080/v1/observability/logs?minutes=30&application=api&source=exception" \
  -H "x-api-key: aijuris"
```

Minimal runnable example:

```bash
python examples/application_insights_logs_demo.py
```

## User profile endpoints

The local API now supports simple profile management for the mobile app using the
same `x-api-key` guard as the chat endpoints.

- `POST /v1/users/sign-up`
  - request: `phone_number`, `email`, `password`, optional `first_name`, `last_name`
  - sends a registration email notification to the new user email
- `POST /v1/users/sign-in`
  - request: `email`, `password`
- `POST /v1/users/sign-in/phone`
  - request: `phone_number`
- `PATCH /v1/users/{user_id}`
  - request: `phone_number`, optional `password`, optional `first_name`, optional `last_name`
  - optional legal-profile fields for document defaults: `address`, `city`, `country`, `zip_code`,
    `tax_number`, `identity_card_number`, `date_of_birth`, `social_security_number`
  - omitted legal-profile fields keep their current values; explicit `null`/empty values clear them
- `GET /v1/users/subscriptions/plans`
  - returns seeded plans: free, case, basic, premium
- `GET /v1/users/{user_id}/subscriptions`
  - returns subscription history for a user
- `POST /v1/users/{user_id}/subscriptions`
  - request: `plan_code`; creates a pending subscription change while old paid plan remains active
  - queues a subscription-change email notification in the email outbox database
- `PATCH /v1/users/subscriptions/{subscription_id}`
  - request: `status` in (`pending`, `paying`, `paid`, `failed`, `canceled`, `expired`)
  - monthly plans start a 30-day window when status changes to `paid`
  - queues an email for every subscription status change (including payment failure)

Privileged test/operator accounts can bypass subscription case count, document upload,
and free-plan case TTL restrictions through `JURISDIGTA_UNLIMITED_ACCESS_EMAILS`.
The value is a comma- or semicolon-separated email allowlist, matched
case-insensitively, and defaults to `mmaideveloper@gmail.com`. Treat this as
privileged access configuration: keep the list small, review it during deployments,
and do not use it for normal customer entitlements.

Generated chat documents can also be sent by email through
`POST /v1/chat/sessions/{session_id}/documents/send-email`. Omit `recipient` to use the
signed-in user's profile email. The first call with `confirmed=false` returns the email address
for confirmation; call again with `confirmed=true` to queue the generated PDF attachments.

Chat sessions with a signed-in user also pass a data-minimized profile note to the lawyer
agent: only the available client name and address are used as default party details in the
prompt. This prevents the assistant from asking again for profile-backed name/address fields
or showing `[nebolo poskytnute]` for them, while keeping stronger identifiers limited to
document-export defaults.

Minimal runnable example:

```powershell
python examples/profile_prompt_defaults_demo.py
```

### Email notification service

### Email outbox + scheduler

Emails are first persisted into a dedicated email database (`email_outbox`) and then delivered by a scheduler.

- Scheduler cadence: every 60 seconds by default (`EMAIL_SCHEDULER_INTERVAL_SECONDS`)
- Retry policy: max 2 attempts. After the second failed attempt, status changes to `failed` and scheduler skips it.
- Queue claiming uses DB-level processing state so multiple scheduler replicas do not pick the same email at once.

Email DB configuration (separate from API metadata DB):

- `EMAIL_DB_OPTION` (`local`/`postgres`/`azure`, default inherits `DB_OPTION`)
- `EMAIL_DB_LOCAL` (default `./runs/storage/api/sqlite/email.sqlite3`)
- `EMAIL_DB_CLOUD` (required for postgres/azure, default inherits `DB_CLOUD`)
- `EMAIL_SCHEDULER_ENABLED` (default `true`)
- When `EMAIL_DB_OPTION` is `postgres` or `azure`, the API does not create local SQLite directories from `EMAIL_DB_LOCAL`.

Postgres/Azure email schema migrations are stored under `databases/api/email`.

Run scheduler as a separate process (recommended for ACA split deployment):

```bash
python -m app.email_scheduler_main
```

Run a one-shot batch for the Azure Container Apps Job:

```bash
python -m app.email_scheduler_job_main
```

For local repo-managed startup, use:

```powershell
.\skills\start-email\scripts\start_email_scheduler.ps1 -Background
```

For API-only replicas set `EMAIL_SCHEDULER_ENABLED=false`; run exactly one scheduler replica/process or ACA Job with delivery enabled.

User and subscription endpoints support email notifications with configurable transport:

- `EMAIL_TRANSPORT=log` (default): logs notifications to API logs (safe for local dev/tests)
- `EMAIL_TRANSPORT=smtp`: sends real emails via SMTP

Corporate contact requests use `POST /v1/contact` without an API key. The endpoint validates the public website payload, rejects honeypot/link spam, verifies Cloudflare Turnstile when `CONTACT_CAPTCHA_REQUIRED=true` or `TURNSTILE_SECRET_KEY` is configured, and sends an email to `info@jurisdigta.eu` through the configured backend email transport.

SMTP configuration (used when `EMAIL_TRANSPORT=smtp`):

- `EMAIL_SENDER` (default: `no-reply@jurisdigta.eu`)
- `EMAIL_SMTP_HOST` (default: `mail.webhouse.sk`)
- `EMAIL_SMTP_PORT` (default: `587`)
- `EMAIL_SMTP_USE_TLS` (default: `true`)
- `EMAIL_SMTP_USERNAME` (default: `EMAIL_SENDER`)
- `EMAIL_SMTP_PASSWORD` (optional)

Email enqueue message composition for these endpoints is centralized in `app/users/notifications.py` to keep endpoint handlers small and reduce merge conflicts with payment/subscription feature work.
- `POST /v1/users/{user_id}/subscriptions/checkout`
  - request: `plan_code`, `payment_provider` (`paypal` or `google_pay`)
  - creates a pending subscription change, sets subscription status to `paying`, and returns a fake checkout URL
- `POST /v1/users/subscriptions/{subscription_id}/confirm-payment`
  - request: `payment_id` returned from checkout
  - payment simulation rule: only user phone `+421944400166` is allowed to complete payment successfully
  - all other phone numbers receive simulated payment failure and the requested subscription is canceled (no upgrade)
  - queues the payment status email notification after the simulated payment result is applied

### Subscription payment flow (PayPal / Google Pay simulation)

### Mobile-app simulation behavior

- The checkout/confirm API path is the same path used by the mobile app integration.
- To test a successful payment upgrade in local/dev, create/sign in a user with phone `+421944400166`.
- To test unsuccessful payment handling, use any other phone number; confirmation returns HTTP `402` and subscription remains not upgraded.

Minimal runnable example:

```bash
python examples/minimal_demo.py
```

```bash
# 1) Start checkout for new subscription
curl -X POST "http://localhost:8080/v1/users/<USER_ID>/subscriptions/checkout" \
  -H "x-api-key: aijuris" \
  -H "Content-Type: application/json" \
  -d '{"plan_code":"premium","payment_provider":"paypal"}'

# 2) Confirm returned payment_id (simulated webhook/callback)
curl -X POST "http://localhost:8080/v1/users/subscriptions/<SUBSCRIPTION_ID>/confirm-payment" \
  -H "x-api-key: aijuris" \
  -H "Content-Type: application/json" \
  -d '{"payment_id":"PAY-..."}'
```

These endpoints persist users through `aijurisdictionagents.api_db.ApiDatabaseStore`
and support three database modes:

- `DB_OPTION=local`: local SQLite metadata (`DB_LOCAL`, default `./runs/storage/api/sqlite/api.sqlite3`)
- `DB_OPTION=postgres`: local PostgreSQL for Docker-based development (`DB_CLOUD=postgresql://...`)
- `DB_OPTION=azure`: Azure Database for PostgreSQL Flexible Server (`DB_CLOUD=postgresql://...sslmode=require`)
  - Use the exact Flexible Server administrator login as the username.
  - In `postgres`/`azure` modes, startup skips creating local SQLite/`runs` folders from `DB_LOCAL`.

The dedicated local database layout guide now lives under `docs/DATABASE_LAYOUT.md`.

## Case history + documents

- `GET /v1/cases/{case_id}/history?user_id=...&offset=0&limit=5` returns the selected case's persisted chat history page plus stored case-document metadata.
- `GET /v1/cases/{case_id}/ai-model-audit?user_id=...&offset=0&limit=50` returns the case model audit trail for authorized case users, including the session, question message, answer message, provider, model, route type, estimated input/output tokens, estimated cost, and a bounded question preview plus SHA-256 hash. The full question remains in the authorized case history instead of being duplicated in the audit ledger.
- `GET /v1/cases/{case_id}/documents/{doc_id}?user_id=...` downloads a previously stored case document or chat attachment.
- `GET /v1/cases/{case_id}/documents/{doc_id}/pdf?user_id=...` renders the client-visible assistant draft tied to a generated technical case document as a PDF, without exposing the stored JSON payload.
- Generated case-document storage sanitizes visible assistant replies before saving document payloads. When one assistant answer contains separate Slovak and English legal drafts, each language is stored as its own `generated_document`; progress text, assistant/system names, apologies, summaries, export/download instructions, raw separators, and raw markdown markers must not be persisted into the PDF body.
- When a linked assistant answer contains conversational setup, summaries, multiple separated language versions, and a generated-document link, the PDF renderer exports the first valid selected legal-document block only. Assistant prose, follow-up instructions, raw markdown separators, raw bold markers, and alternate-language drafts are excluded unless they are part of that selected document block.
- If the original technical-payload marker is no longer present in the latest case history window, the generated case-document PDF endpoint falls back to the newest assistant message that contains a finalized document body and renders only that document body, not the surrounding chat text.
- Generated case-document PDF downloads use a user-facing filename format: normalized case title, document GUID, and normalized document type, for example `payment-confirmation_<doc_id>_potvrdenie.pdf`; the visible PDF heading and PDF metadata title also use the detected document type such as `Potvrdenie`, so browser PDF tabs do not show `untitled`.
- `GET /v1/cases/{case_id}/documents/context?user_id=...` now reports processed/unprocessed memory inputs across uploaded files, chat attachments, and generated `session_history` transcripts.
- If a transcript or document payload is missing in local storage, history responses fall back to saved summaries and document download returns `404` instead of `500`.
- Uploaded case documents are stored as `case -> many documents`. Each processed uploaded document keeps the extracted full text plus a real embedding in `case_document_contents`, and chunk-level text/embedding rows in `case_document_chunks`.
- Case-backed chat streams now persist inline session documents as reusable case attachments, process them immediately in local/API mode, and refresh the per-session `session-{session_id}.txt` transcript document on every later turn in the same session.
- Direct `POST /v1/chat/sessions/{session_id}/reply` now loads the most relevant processed document chunks for the user query by combining lexical overlap with semantic similarity from real embeddings, then injects those chunks into the extra system-context document message.
- Slovak share-transfer intake now prefers labeled company fields such as `Nazov:` / `Názov:` / `Obchodné meno:` when extracting the ORSR lookup query, so owner names in later lines do not override the company verification step.
- `POST /v1/chat/sessions/{session_id}/stream` in `ReadUser` mode now emits intermediate `processing` SSE events for the company-verification path, including ORSR tool start/result and which drafting inputs were detected vs. still missing.
- Slovak share-transfer intake is now selective: if the user already supplied the transferee details or said the transfer is `bezodplatne`, the assistant asks only for the remaining missing items instead of repeating the same checklist.
- The Slovak share-transfer intake parser now also recognizes inline numbered one-line inputs such as `Dalsi vlastnik: ... 2. Podiel sa prevádza bezodplatne. 3. Nemení iba spoločnícka štruktúra ...`, so chatsimulator cases do not lose those facts just because the user typed everything in a single paragraph.
- Direct assistant clarification turns now enforce one-question-at-a-time behavior: when extra data is required, the API keeps only the highest-priority follow-up question in that turn and truncates `CASE_UPDATE_JSON.case.open_questions` to a single item.
- User-facing chat payloads no longer expose raw `CASE_UPDATE_JSON` or bare JSON/XML technical trailers; API stores hidden technical payloads as case documents, adds the case-document URL to the friendly assistant text, and returns only visible assistant text in `/reply`, `/messages`, case history, and streaming `message` events.
- Local API starts through [skills/start-api/scripts/start_api.ps1](/C:/Users/maton/Projects/aijurisdictionagents/skills/start-api/scripts/start_api.ps1) now enable `LOCAL_LLM_IO_LOGGING=1` by default, so local logs include the exact model payload and raw model response for debugging without changing deployed environments.
- Local API starts bound to `127.0.0.1`, `localhost`, or `::1` also set `LOCAL_AUTH_ACCEPT_ANY_CODE=1`, allowing any 4-8 character verification code for local registration/sign-in testing only. Keep this disabled in deployed environments.
- The mobile app uses these endpoints to show the latest 5 saved case messages after case selection and to expose case-document download buttons.
- If an older case-history transcript blob is missing or unreadable, the API now falls back to the stored communication summary instead of failing the history load or blocking new session creation for that case.

## PDF export

- `GET /v1/chat/sessions/{session_id}/export?format=pdf&kind=summary` returns the session summary.
- The summary PDF now includes generation date, API version, system core version, the latest law update date available to the system, the law-update source, the final recommendation for the user case, official law links stored by the law processor, and a dedicated case-validation section at the end with accuracy and validation summary.
- When the user asks to review and recreate an uploaded document under current law, the summary PDF also includes a dedicated legal-basis section that states which legal dataset and official law links were used to evaluate the document.
- `GET /v1/chat/sessions/{session_id}/export?format=pdf&kind=document` now builds a document that matches the detected case topic instead of always returning a lease template.
- Client-facing legal documents, including requests such as `potvrdenie o zaplateni`, now render with the professional JurisDigta template layout plus a footer QR code containing traceability metadata: generation date, API version, core system version, case ID, session ID when available, user ID when available, and document verification score. The footer also shows the document verification score; when that score is unknown or below `DOCUMENT_SHOW_DISCLAIMER` (default `50`), the PDF adds the legal-draft warning on a final standalone page.
- Payment-confirmation exports are detected before older rental/easement case context, so a request for `potvrdenie o zaplateni` does not reuse a stale lease or pre-litigation-demand body. Generated PDF lines also repair common Slovak mojibake before rendering.
- Exported law citations identify the laws connector DB as source score `1.0`. If a future export has no managed template or relevant laws-DB source and must fall back to `AIWebSearchAgent`, the internet source must be logged with URL/title and source score `0.9`.
- Single-document exports derive the visible PDF title from the lawyer recommendation and detected legal document type, such as `Najomna zmluva` or `Kupno-predajna zmluva`, instead of displaying the session ID.
- The document exporter now derives the topic from the full session context, not only from explicit lawyer draft blocks, so Slovak company share-transfer / new-owner sessions generate a targeted transfer-package draft instead of a generic memo.
- Minimal runnable examples: `python examples/share_transfer_export_demo.py` and `python examples/payment_confirmation_export_demo.py`
- Direct `POST /v1/chat/sessions/{session_id}/reply` sessions also persist a session result now, so the mobile `Real Agent` flow can download PDFs without going through the simulator stream.
- In `Real Agent` mode, the lawyer can first ask whether a formal document should be prepared as PDF; once the user confirms, the next direct reply marks `metadata.document_ready=true` in `GET /v1/chat/sessions/{session_id}/result`.
- Explicit document-revision requests that mention uploaded documents plus update/fix wording such as reviewing a contract against newer laws are also treated as document-preparation requests, so the API can prepare an updated export without waiting for a separate summary-only path.
- `GET /v1/chat/sessions/{session_id}/result` metadata now also includes `last_law_update_date`, `last_law_update_source`, `model_knowledge_cutoff_date`, `model_knowledge_cutoff_source`, `law_reference_links`, `law_citations`, `api_version`, and the backward-compatible `knowledge_last_updated_at` alias.
- `GET /v1/laws/source?...` streams the stored full-law source for a resolved citation. For local imports it reads the persisted local file, and for Azure imports it reads the same artifact from Blob storage.
- `GET /v1/laws/statistics?country_code=SK` returns law collector progress and corpus counters, including the last processed law/date, total imported/finalized laws, total versions, versions without embeddings, laws without embeddings, archive asset counts, and year coverage.

Citation payload demo:

```bash
python examples/law_citation_resolution_demo.py
```
- When the laws database has no import timestamp yet, `knowledge_last_updated_at` falls back to the cached `MODEL_KNOWLEDGE_CUTOFF_DATE` value while `last_law_update_date` remains empty.
- For Slovak and other Central European locales, the exporter uses a Unicode TrueType font when available so characters such as `á`, `č`, `ľ`, `ô`, and `ž` render correctly in the generated PDF.
- For Slovakia (`country=SK` or language `sk-*`), document PDFs now include a Slovak legal-document profile header (`Jurisdikcia: Slovenská republika`, `Typ dokumentu: právny návrh`) to make exports closer to expected local legal formatting.

Additional PDF font notes:
- The API container installs `fonts-dejavu-core` and the exporter prefers `DejaVu Serif` on Linux, so Azure deployments do not fall back to Helvetica for Slovak or German PDFs.
- If DejaVu is unavailable on Linux, the exporter now falls back to `Liberation Serif` / `Liberation Sans` before trying platform-default fonts.
- On Windows, the exporter prefers `Times New Roman` and then `Arial` for Central European PDF exports.

## Document template catalog

- `GET /v1/document-templates` lists the persistent legal-template catalog used for future template-driven contract generation.
- `POST`, `PATCH`, and `DELETE` on `/v1/document-templates/*` allow templates to be added, updated, and soft-deleted without changing code.
- `GET /v1/document-templates/match/search?request_text=...&country=SK` returns the best matching template candidate for a client request.
- Templates now support optional `disclaimer_title`, `disclaimer_text`, and `disclaimer_footer` fields so legal disclaimer wording can be updated without a code deploy.
- Template preview PDFs and chat-generated Slovak document PDFs render the disclaimer on page one and repeat the short disclaimer in the footer.
- The initial seed contains the common Slovak template groups supplied for:
  - commercial/corporate contracts
  - employment/personnel documents
  - court filings
  - powers of attorney
  - real-estate / lease contracts
- Seed records can start as metadata-only (`source_url`, `source_format`, keywords, category) and later be enriched with a full template body for rendering.
- Template runtime storage defaults to `runs/storage/api/sqlite/document_templates.sqlite3`.
- Detailed API notes: `docs/DOCUMENT_TEMPLATES_API.md`
- Minimal runnable example: `python examples/document_templates_minimal_demo.py`

## Version bump workflow

Rule:
- Whenever API or system core code changes, increase the revision number in the corresponding version file in the same change.
- Unless explicitly requested otherwise, do not change major or minor version numbers for these routine updates.

When API code changes:
1. Bump `version` in `api/aijuristiction-api/pyproject.toml`.

When core (`/src`) code changes:
1. Bump `__version__` in `src/aijurisdictionagents/__init__.py`.
2. Bump `[project].version` in root `pyproject.toml`.

When chat simulator code changes:
1. Bump `version` in `api/chat-simulator-app/pyproject.toml`.
2. Bump `version` in `api/chat-simulator-app/app/main.py`.

## Swagger and authentication

- Swagger UI (local): `http://localhost:8080/docs`
- OpenAPI JSON (local): `http://localhost:8080/openapi.json`
- Chat endpoints under `/v1/chat/*` require header:
  - `x-api-key: aijuris` (currently hardcoded for initial integration)

Example:

```bash
curl -X POST "http://localhost:8080/v1/chat/sessions" \
  -H "Content-Type: application/json" \
  -H "x-api-key: aijuris" \
  -d "{}"
```

## CORS for local simulator

- API enables CORS for local development origins by default:
  - `http://localhost:<any-port>`
  - `http://127.x.x.x:<any-port>` for loopback IPv4 addresses
  - `http://[::1]:<any-port>` for IPv6 loopback
  - `Origin: null` for static `file://` previews, including the corporate web contact form during local checks
- Deployed browser clients are blocked until `CORS_ALLOW_ORIGINS` includes their exact origins. The self-managed production deploy always adds `https://web.jurisdigta.eu` and `https://agent.jurisdigta.eu` for the API container.
- Native Android/iOS builds do not require `CORS_ALLOW_ORIGINS`.
- Override allowed origins with `CORS_ALLOW_ORIGINS` (comma-separated), for example:

```bash
CORS_ALLOW_ORIGINS=http://localhost:8090,http://127.0.0.1:8090,http://localhost:7357,http://127.0.0.1:7357 uvicorn app.main:app --reload --port 8080
```

Example for a deployed browser build:

```bash
CORS_ALLOW_ORIGINS=https://mobile-web-dev.example.com,https://web-juris-dev.<region>.azurecontainerapps.io,https://web.jurisdigta.eu,https://agent.jurisdigta.eu uvicorn app.main:app --reload --port 8080

## Local source precedence

- The local startup script `skills/start-api/scripts/start_api.ps1` now prepends both `api/aijuristiction-api` and repo `src/` to `PYTHONPATH`.
- This ensures local API runs use the current repository source code for `aijurisdictionagents` instead of an older installed site-packages build.
- If local behavior does not match the checked-out repo code, restart the API through the startup script rather than reusing an older Python process.
```

## Chat simulator

The chat simulator has been moved to a separate application: `api/chat-simulator-app`.

Run it independently to test chat flows before frontend deployment.

For persisted-case debugging with local PostgreSQL, start the API with:

```bash
DB_OPTION=postgres DB_CLOUD=postgresql://postgres:postgres@127.0.0.1:5432/aijurisdiction STORAGE_OPTION=local DOCUMENT_PROCESSOR_OPTION=api LOCAL_LLM_IO_LOGGING=1 uvicorn app.main:app --reload --port 8080
```

The simulator can then call `GET /v1/cases/{case_id}/documents/debug?user_id=...&query=...` to show:
- stored uploaded document rows from the API database
- embedding/vector presence and chunk counts
- the exact document chunks selected for prompt injection for a query

For Slovak simulated discussions, the AI user now ends the conversation with `To je vsetko` instead of the internal sentinel word `finish`.

## OpenTelemetry

- Recommended production path: set `APPLICATIONINSIGHTS_CONNECTION_STRING` and the API will export requests, traces, logs, and unhandled exceptions to Azure Monitor / Application Insights.
- The API keeps writing structured request logs to console, so ACA log streaming and Log Analytics remain available even when Application Insights is enabled.
- To enable the `/v1/observability/logs` API in Azure, the deployed Container App also needs:
  - `AZURE_LOG_ANALYTICS_WORKSPACE_NAME`
  - `AZURE_MANAGED_IDENTITY_NAME`
  - `AZURE_RESOURCE_GROUP`
  - `AZURE_SUBSCRIPTION_ID`
- Repository Azure deploys populate those values automatically from the shared Log Analytics workspace and the configured user-assigned managed identity. They also set the standard `AZURE_CLIENT_ID` environment variable on the Container App so Azure SDK auth selects the intended user-assigned identity.
- The user-assigned managed identity should have `Log Analytics Data Reader` on the target Log Analytics workspace.
- Fallback behavior:
  - If `APPLICATIONINSIGHTS_CONNECTION_STRING` is set, Azure Monitor OpenTelemetry is used.
  - Else if `OTEL_EXPORTER_OTLP_ENDPOINT` is set, traces are exported to that OTLP endpoint.
  - Else traces are written via the console exporter.
- `OTEL_SERVICE_NAME` defaults to `aijuristiction-api` if not set explicitly.
- Console trace export uses a synchronous processor in local default mode to avoid shutdown-time exporter thread errors during tests.

Local Azure Monitor example:

```bash
APPLICATIONINSIGHTS_CONNECTION_STRING="InstrumentationKey=..." uvicorn app.main:app --reload --port 8080
```

Local OTLP fallback example:

```bash
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318/v1/traces uvicorn app.main:app --reload --port 8080
```


## Database schema updates (local + cloud)

The API now applies SQL migrations during app startup for PostgreSQL/Azure, then runs the in-code bootstrap/compatibility checks. SQLite remains code-driven.

For pre-deploy validation, run from repository root:

```bash
PYTHONPATH=src python scripts/databases/apply_db_migrations.py --project api --dry-run
PYTHONPATH=src python scripts/databases/apply_api_db_schema.py --dry-run
PYTHONPATH=src python scripts/databases/apply_db_migrations.py --project api
PYTHONPATH=src python scripts/databases/apply_api_db_schema.py
```

Local PostgreSQL example:

```bash
.\skills\start-postgres\scripts\start_postgres.ps1 -SkipSchemaUpdate
DB_OPTION=postgres DB_CLOUD=postgresql://postgres:postgres@localhost:5432/aijurisdiction STORAGE_OPTION=local PYTHONPATH=src python scripts/databases/apply_api_db_schema.py
```

Cloud rollout:
1. Build/push/deploy API image.
2. Provision or update Azure PostgreSQL Flexible Server (`db-juris-dev` by default) through infra deployment.
3. Confirm Container App configuration:
   - `DB_OPTION=azure`
   - `DB_CLOUD=secretref:db-cloud`
   - `STORAGE_OPTION=azure`
   - `STORE_CLOUD=https://<storage-account>.blob.core.windows.net/<container-name>`
4. Confirm the API revision also gets laws metadata access:
   - `LAWS_COUNTRY=SK`
   - `LAWS_DB_BACKEND=postgres`
   - `LAWS_DB_CLOUD=secretref:laws-db-cloud`
5. Roll out a new revision (or restart) and verify startup logs include selected `db_option`.

Model metadata demo:

```bash
python examples/model_knowledge_cutoff_demo.py
```

ACA log access:

```powershell
.\infra\scripts\tail_api_logs.ps1 -Tail 200
.\infra\scripts\tail_api_logs.ps1 -Tail 200 -CorrelationId "<mobile-correlation-id>"
```

The API echoes both `x-request-id` and `x-correlation-id` in responses, and ACA request logs include those values for direct filtering.

Application Insights and alerts:

- In ACA, set `APPLICATIONINSIGHTS_CONNECTION_STRING` as a secret-backed environment variable.
- The infra deployment now provisions or reuses the Application Insights resource `ai-juris-dev` by default and applies its connection string to the API Container App automatically.
- Recommended alert sources:
  - failed requests / HTTP 5xx
  - `AppExceptions` count
  - ACA system logs for revision or container failures
- Example KQL for recent API exceptions:

```kusto
AppExceptions
| where TimeGenerated > ago(1h)
| order by TimeGenerated desc
| project TimeGenerated, ProblemId, Message, InnermostMessage, OperationName
```

- Example KQL for failed requests:

```kusto
AppRequests
| where TimeGenerated > ago(30m)
| where Success == false
| order by TimeGenerated desc
| project TimeGenerated, Name, ResultCode, DurationMs, OperationId
```

GitHub workflows:

- `.github/workflows/infra_deploy.yml`: provisions or updates Azure infrastructure, including PostgreSQL Flexible Server
- `.github/workflows/api_build_deploy.yml`: builds and deploys the API image, applies schema updates to Azure PostgreSQL, and injects `APPLICATIONINSIGHTS_CONNECTION_STRING` into ACA when the GitHub Environment secret is present
- `.github/workflows/database_schema_upgrade.yml`: upgrades schema on an existing Azure PostgreSQL server without rebuilding or redeploying the API

## Build + deployment workflow

GitHub workflow: `.github/workflows/api_build_deploy.yml`

Before opening a PR from a feature branch, sync it with latest `main`:

```bash
git fetch origin
git merge origin/main
```

- CI checks: install deps, lint (`ruff`), type-check (`mypy`), tests (`pytest`), and Docker build.
- GitHub Actions installs both the repo root package (`pip install -e ../..`) and the API package (`pip install -e .[dev]`) so tests can import `../../src/aijurisdictionagents` with its runtime dependencies.
- Local pre-flight command to mirror CI from this folder:

```bash
ruff check . && mypy app && pytest -q
```

Typing note: keep `UserResponseProvider` and `MessageCallback` imports in `app/chat/core_runtime.py`
inside the `TYPE_CHECKING` block so both `ruff` and `mypy --strict` stay green.
Database cursor reads in `app/chat/result_metadata.py` intentionally go through typed helper wrappers so strict `mypy` does not treat `fetchone()` results as implicit `Any`.

Telemetry processor selection (OTLP vs console) is covered by unit tests in `tests/test_telemetry.py`.

The API `pyproject.toml` also sets `mypy_path = ["../../src"]` so strict type checks can resolve the monorepo core package during CI and local runs.
The `pytest` command is configured with `pythonpath = [".", "../../src"]` in `pyproject.toml`, so tests can import the monorepo core package during direct local runs and GitHub Actions.
- Deploy path: on manual dispatch with `deploy=true`, push image to Azure Container Registry and deploy/update Azure Container App.

Required GitHub Environment variables:
- `AZURE_CLIENT_ID`
- `AZURE_TENANT_ID`
- `AZURE_SUBSCRIPTION_ID`
- `AZURE_RESOURCE_GROUP`
- `AZURE_CONTAINERAPPS_ENVIRONMENT`
- `AZURE_CONTAINER_APP_NAME`
- `AZURE_CONTAINER_REGISTRY`

The workflow dispatch input `github_environment` selects which GitHub Environment
supplies these variables.
`AZURE_CONTAINER_REGISTRY` should be the registry name (example: `arcjuris`).
The workflow also normalizes values like `arc-juris.azurecr.io` to `arcjuris`.

For Azure OIDC federation setup (GitHub -> Entra app federated credential for
`AZURE_CLIENT_ID`), see `infra/README.md` section `GitHub workflow deployment setup (OIDC federation)`.

## E2E testing recommendation

Because you are familiar with Playwright, use **Playwright API testing** (`APIRequestContext`) for API E2E:

1. Run tests from `e2e-playwright/` (API auto-start is enabled by default).

```bash
cd api/aijuristiction-api/e2e-playwright
npm install
npx playwright test
```

Playwright auto-start details:
- Default behavior: starts API before tests when `API_BASE_URL` is not set.
- If `API_BASE_URL` is set, Playwright targets that URL and does not auto-start local API unless `PW_START_API=1`.
- Existing local API is not reused by default. Set `PW_REUSE_EXISTING_SERVER=1` to reuse one.
- Python resolution order for local API start:
  1. `API_PYTHON`
  2. repo local `.conda` interpreter
  3. `python`/`py` from PATH

Current E2E specs:
- `tests/health.spec.ts`
- `tests/version.spec.ts`
- `tests/chat.spec.ts`
- `tests/chat-simulator.spec.ts`
- `tests/mobile-auth-subscription.spec.ts` (covers mobile login + subscription request flow against user endpoints)
- Negative auth test in `tests/chat.spec.ts` runs only when `RUN_NEGATIVE_AUTH_TESTS=1`.

Run only the chat simulation test:

```bash
cd api/aijuristiction-api/e2e-playwright
API_KEY=aijuris npx playwright test tests/chat.spec.ts
```

On Windows PowerShell:

```powershell
cd api/aijuristiction-api/e2e-playwright
$env:API_KEY="aijuris"
npx playwright test tests/chat.spec.ts
```

Run chat test with negative auth coverage enabled:

```bash
cd api/aijuristiction-api/e2e-playwright
RUN_NEGATIVE_AUTH_TESTS=1 npx playwright test tests/chat.spec.ts
```



Run the mobile authentication + subscription lifecycle check used by the Flutter app:

```bash
cd api/aijuristiction-api/e2e-playwright
API_KEY=aijuris npx playwright test tests/mobile-auth-subscription.spec.ts
```

Run the chat simulator streaming test with fixture input and uploaded txt document:

```bash
cd api/aijuristiction-api/e2e-playwright
API_KEY=aijuris npx playwright test tests/chat-simulator.spec.ts
```

The test persists question/answer review output to the Playwright test-results folder as `chat-simulator-qa.json` and attaches it to the report.

For simulator-style streaming automation, the stream payload also supports:
- `communication_minutes`: how long simulated user responses are allowed
- `user_simulation_mode`: `ReadUser` (default) or `AIUserSimulatorAgent`
- Lawyer asks about PDF export only after clarifying questions are resolved.
- In `AIUserSimulatorAgent` mode, the closing sequence is automated:
  - answer each AI agent question first
  - request PDF result
  - send thank-you
  - send `finish` to close discussion
- AI user simulation now uses full conversation context and avoids exact repeated replies across turns.
- AI user simulation normalizes non-answer outputs (questions/clarification requests) into factual continuation replies.

PDF export options:
- `GET /v1/chat/sessions/{session_id}/export?format=pdf&kind=summary` -> discussion summary PDF
- `GET /v1/chat/sessions/{session_id}/export?format=pdf&kind=document` -> generated lawyer document PDF
- Summary PDF includes `AI Jurisdiction` branding and session metadata (session ID, country, language).
- Document PDF (`kind=document`) includes:
  - one-line header: `AI Jurisdicta Solution | Generated: <timestamp>`
  - one-line footer: `AIJ | API <api_version> | Core <core_version>`
  - right-top logo mark (`AI Jurisdicta [AIJ]`)
- Document PDF uses a formal legal-agreement structure (articles/clauses and signature fields) when generating final contract output.
- To smoke-test Slovak and German glyph rendering locally, run `python examples/minimal_pdf_export.py` and open `runs/minimal-pdf-export.pdf`.
- PDF filenames:
  - document/final: `{case_id}-{yyyyMMddHHmmss}-final-document.pdf`
  - summary: `{case_id}-{yyyyMMddHHmmss}-discussion-summary.pdf`

Run only the version endpoint test:

```bash
cd api/aijuristiction-api/e2e-playwright
npx playwright test tests/version.spec.ts
```

This approach keeps one tool for UI + API E2E while still allowing pytest integration tests for backend internals.

### Behavior when API is not running

Playwright E2E tests target a live API and fail fast if the API is unavailable.

- When auto-start is enabled and Python is missing, run fails immediately with startup error.
- When targeting an external `API_BASE_URL`, each test checks `/health` and fails with connection details if unavailable.
- To tune readiness probe timeout, set `API_HEALTH_TIMEOUT_MS` (default `2000`).


## Current Task #7 progress

- Subtask 1 complete: architecture RFC + ADR (`docs/API_ARCHITECTURE_RFC.md`, `docs/adr/ADR-0001-api-framework-and-streaming.md`).
- Subtask 3 started: in-memory session/message domain model and initial chat endpoints.

New endpoints:
- `POST /v1/chat/sessions`
- `POST /v1/chat/messages`
- `POST /v1/chat/sessions/{session_id}/reply` (store user message and generate immediate lawyer answer)
- `GET /v1/chat/sessions/{session_id}/messages`
- `POST /v1/chat/sessions/{session_id}/stream` (SSE streaming from core orchestrator)
- `GET /v1/chat/sessions/{session_id}/result`
- `GET /v1/chat/sessions/{session_id}/export?format=json|pdf&kind=summary|document` (`kind` applies to `pdf`)
- `GET /v1/chat/sessions/{session_id}/export/documents` lists individual PDF documents available for a session, and `GET /v1/chat/sessions/{session_id}/export/documents/{index}` downloads one selected PDF instead of forcing a multi-document ZIP.

If `POST /v1/chat/sessions` is created with `case_id`, the API now seeds that new in-memory session with the stored case history so the next reply/stream turn can continue the existing case context instead of starting with an empty prompt.
If one of those seeded case-history transcript files is missing, the API falls back to the saved summary text so existing cases can still create a session and continue.
Case-backed session `3` can now also reuse documents uploaded during session `1` and session `2`, because inline chat documents are persisted into case memory and refreshed session-history transcripts are reprocessed for later retrieval.


## Minimal runnable example (streaming API + core)

Start API first, then run:

```bash
python examples/api_streaming_demo.py
```

Cross-session memory formatting demo:

```bash
python examples/conversation_memory_minimal_demo.py
```
