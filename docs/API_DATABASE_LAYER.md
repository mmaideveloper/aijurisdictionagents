# API database layer (local + PostgreSQL Docker + Azure-ready)

## Recommended approach

For your feature set, use a **hybrid model**:

1. **Relational SQL database** for metadata and relationships.
2. **Object storage** for document/audio binaries.

## Environment variables (local + cloud)

Use these environment variables in local `.env`, Docker, and GitHub environment secrets.

- `DB_OPTION`: `local`, `postgres`, or `azure`
- `STORAGE_OPTION`: `local` or `azure`
- `DB_LOCAL`: local SQLite path relative to the repo root (example: `./runs/storage/api/sqlite/api.sqlite3`)
- `DB_CLOUD`: cloud database connection string (PostgreSQL in Azure)
- `STORE_LOCAL`: local storage root path (example: `./runs/storage/api/files`)
- `STORE_CLOUD`: Azure Blob URL prefix for case artifacts (example: `https://<storage-account>.blob.core.windows.net/<container-name>`)

If you set:
- `DB_OPTION=postgres`, then `DB_CLOUD` is required.
- `DB_OPTION=azure`, then `DB_CLOUD` is required.
- `STORAGE_OPTION=azure`, then `STORE_CLOUD` is required.

This aligns with your GitHub environment secrets plan:
- `DB_OPTION=azure`
- `STORAGE_OPTION=azure`
- `DB_CLOUD=...`
- `STORE_CLOUD=...`

Azure Database for PostgreSQL Flexible Server uses the configured
administrator login as the connection string username. Example:

```text
postgresql://jurisadmin:<password>@db-juris-dev.postgres.database.azure.com:5432/aijurisdiction?sslmode=require
```

## Concrete technology choice

### Phase 1 (now): local + Docker + basic cloud portability

- **SQLite** for metadata (`runs/storage/api/sqlite/api.sqlite3`) when `DB_OPTION=local`.
- **PostgreSQL** for metadata when `DB_OPTION=postgres` (recommended via Docker locally).
- Filesystem blob folder for stored assets.

### Phase 2 (production): scalable and resilient

- **Azure Database for PostgreSQL** for metadata.
- **Azure Blob Storage** for documents/audio/generated files.


## Case-scoped storage layout

For both local and azure modes, all case artifacts are written under a `case_id` folder/prefix:

- Documents: `<case_id>/<kind>/v<version>_<filename>`
- Communications: `<case_id>/communications/<communication_id>.<ext>`

This guarantees every case has an isolated storage namespace.

## Supported domain entities

- `users`: sign-up and login metadata.
- `companies`: company profile.
- `company_users`: user/company association and role.
- `cases`: user/company legal cases.
- `case_documents`: source/generated document metadata + versions.
- `case_communications`: chat/audio transcript references and summaries.
- `case_citations`: privacy-minimized legal source metadata linked to case questions and assistant answers.

`case_citations` stores source type, stable source id or safe URL, display label, law/court metadata where available, a short snippet, retrieval tool, optional relevance score, and creation time. It intentionally does not store full retrieved law bodies, raw court-decision text, prompts, or sensitive case/user content. Case history returns citations attached to each answer, and `/v1/cases/{case_id}/citations` returns the authorized aggregate list for the case citation panel.

## Minimal demo

```bash
PYTHONPATH=src python examples/api_database_minimal_demo.py
```

Azure config-only demo:

```bash
PYTHONPATH=src python examples/azure_api_postgres_config_demo.py
```

## Docker notes

Run local PostgreSQL stack from repository root:

```powershell
.\skills\start-postgres\scripts\start_postgres.ps1
```

Mount volumes for local mode:
- repo `runs/storage/api/sqlite` for API SQLite metadata
- repo `runs/storage/api/files` for `STORE_LOCAL`
- Docker PostgreSQL persistence root: `runs/storage/api/postgres/data`
- Legacy local PostgreSQL data is migrated into `runs/storage/api/postgres` on first managed startup.

Run the full local Docker stack (API + PostgreSQL):

```bash
cd api/aijuristiction-api
docker compose up --build
```

The API compose build now uses the repository root as context so the container includes the shared `src/aijurisdictionagents` package plus SQL assets under `databases/api/` and `databases/laws-collector/`.
Do not run the API compose stack and the standalone `start-postgres` API instance at the same time because both use the same PostgreSQL data directory.


## Schema update workflow

`ApiDatabaseStore.initialize()` is idempotent and now serves as the schema bootstrap/migration step for SQLite and PostgreSQL.

Run migrations explicitly before testing/deploying:

```bash
PYTHONPATH=src python scripts/databases/apply_api_db_schema.py --dry-run
PYTHONPATH=src python scripts/databases/apply_api_db_schema.py
```

### Local PostgreSQL + Docker

```bash
.\skills\start-postgres\scripts\start_postgres.ps1 -SkipSchemaUpdate
DB_OPTION=postgres DB_CLOUD=postgresql://postgres:postgres@localhost:5432/aijurisdiction STORAGE_OPTION=local PYTHONPATH=src python scripts/databases/apply_api_db_schema.py
```

### Cloud rollout checklist (Azure)

1. Deploy code/image to Container Apps.
2. Ensure Container App configuration includes:
   - `DB_OPTION=azure`
   - `DB_CLOUD` sourced from a Container Apps secret
   - `STORAGE_OPTION=azure`
   - `STORE_CLOUD` set to the Azure Blob URL prefix
3. Restart/revision rollout the Container App; startup now runs schema initialization automatically.
4. Verify with health endpoint and logs (`db_option=azure` at startup).

## Azure Container Apps notes

- Use a secret for `DB_CLOUD`.
- `STORE_CLOUD` is a blob URL prefix, not a storage account key/connection string.
- Keep `DB_OPTION=azure` and `STORAGE_OPTION=azure`.
- `infra/scripts/deploy_api.ps1` now generates the Azure PostgreSQL connection string, stores it as a Container Apps secret, and points `DB_CLOUD` at that secret reference automatically.
- This commit validates env contracts; production adapters can be plugged in next.

## Subscription model (Task #86)

The API database now seeds four subscription plans and tracks user subscription lifecycle:

- `free` (`none`): assigned on sign-up, max 1 case, 1 day case TTL.
- `case` (`perCase`): €10, max 1 case, unlimited case time, assigned to user/case usage.
- `basic` (`monthly`): €30/month, max 10 cases.
- `premium` (`monthly`): €100/month, max 100 cases.

Status model: `pending`, `paying`, `paid`, `canceled`, `expired`.
For monthly plans, `starts_at` and `ends_at` are set when status switches to `paid`.
Runtime entitlement checks treat a paid subscription as active only when its
`starts_at` has begun and `ends_at` is empty or in the future. Expired paid
subscriptions fall back to the Free plan, which also keeps chat model routing on
the local Ollama route instead of an external provider.
The public `/v1/model-routing/effective` endpoint exposes only effective route
metadata (`plan_code`, `route_type`, provider, model, and label) so clients can
display the same model route the backend will use without exposing prompts,
secrets, or case content.

`role=admin` users and `JURISDIGTA_UNLIMITED_ACCESS_EMAILS` users receive an
internal synthetic `unlimited` plan at runtime so case-count limits,
document-upload limits, and free-plan write TTL restrictions do not apply.
`JURISDIGTA_UNLIMITED_ACCESS_EMAILS` remains a comma- or semicolon-separated
case-insensitive allowlist for controlled non-admin test/operator accounts. The
setting defaults to `mmaideveloper@gmail.com` and should stay limited to explicitly
approved accounts for GDPR/EU AI Act traceability and human-oversight controls.

When a write request targets a case after its plan edit window has expired, API
403 responses use a structured `detail` object with code
`case_write_window_expired`, a fallback English `message`, and `params.plan` /
`params.days`. Frontends must translate the code locally instead of displaying
the fallback backend text directly.

Minimal runnable example:

```bash
python examples/subscription_minimal_demo.py
```

## AI Model Routing And Usage Ledger (Task #365)

The API database now includes a policy-driven model routing foundation:

- `ai_model_providers`: local or external provider metadata such as `local_ollama`, `azure_foundry`, `openai`, base URL, region, data zone, API version, and health URL.
- `ai_model_profiles`: provider model/deployment metadata plus context window, default-free-plan marker, and price-per-1M-token metadata.
- `ai_model_credentials`: encrypted provider secrets such as API keys or Azure AD tokens. The runtime decrypts these only when a selected route needs them; admin endpoints redact secret values unless an authorized admin explicitly requests reveal.
- `ai_model_groups` and `ai_model_group_users`: optional assignment of users to model groups for staged rollout or premium routing.
- `ai_model_user_overrides`: one current per-user direct model override. Admins can assign any enabled local or external model profile to a user, update the assignment, or disable it with a mandatory reason. Disabled rows remain for operational traceability while `ai_model_admin_audit_events` preserves create/update/disable history.
- `ai_task_route_policies`: task type plus plan policy with preferred local/external profile, external acknowledgement, EU data-zone requirement, local fallback flags, and optional `max_cost_eur` budget caps.
- `ai_model_usage_ledger`: per-request token and estimated cost ledger by user, subscription, case, task type, provider, model, route, and time. Case audit fields also store `session_id`, `question_id`, bounded `question_preview`, `question_sha256`, `answer_id`, and minimal audit metadata so JurisDigta can show which model answered which question without duplicating full legal prompts outside the case history.
- `ai_model_admin_audit_events`: admin-only model/provider/group/policy and operational case-reset change trail with actor email, entity, old/new summaries, reason, correlation id, and timestamp. It stores metadata summaries only and must not contain legal case text or provider secrets.
- `users.role` and `users.is_enabled`: global user/admin role and account status used by `/app/admin` and admin APIs.

Admin management is exposed through `GET/POST /v1/admin/ai-models...`, `GET/PATCH /v1/admin/users...`, `GET/DELETE /v1/admin/cases...`, and the React route `/app/admin`.
Production admin access is server-authorized from `cf-access-authenticated-user-email` with either database `role=admin` or `JURISDIGTA_ADMIN_EMAILS`; local development may send `x-jurisdigta-admin-user-id` from loopback only.
For the production web app, email/password or MFA sign-in returns a device-bound token when the browser supplies `device_id`; `/app/admin` sends `x-jurisdigta-admin-user-id`, `x-jurisdigta-device-id`, and `x-jurisdigta-device-token`, and the API verifies the hashed device token before accepting the admin role. Do not trust the browser-stored role by itself for admin API authorization.

Web MFA login challenges expire after 10 minutes and are single-use, including after an unsuccessful verification attempt. This limits replay and brute-force opportunities. When verification reports an invalid or expired challenge, the web client must discard its challenge token, remove the MFA form, and re-enable password sign-in so the user can obtain a fresh challenge without refreshing the page. Client and server logs must not include the MFA token, TOTP secret, or verification code; this preserves data minimization while keeping the authentication transition traceable at the request level.
Keep external-provider API keys in backend secrets and store only provider references, base URLs, deployment names, data-zone flags, prices, and health URLs in these tables.
Provider deletion is soft-delete only. `DELETE /v1/admin/ai-models/providers/{provider_id}` sets provider delete metadata, disables the provider, disables linked model profiles and credentials, and records a `provider.soft_delete` audit event without returning or logging provider secrets. Deleted providers stay in the database and audit trail, but dashboard tables, routing, and normal selectable provider lists exclude deleted providers.
Admin routing records use the same table-first lifecycle pattern: Providers, `Modely a ceny`, `Používateľské skupiny`, and `Smerovacie politiky` first show active records in a table, then expose Add/Edit forms with Save/Cancel. Delete operations for providers, model profiles, groups, and route policies are soft deletes with audit events and are hidden from normal Admin tables after refresh. Default free model profiles and profiles referenced by enabled route policies cannot be deleted until the default or policy reference is changed.

Chat model provider, model, deployment, and credentials are resolved from these database tables, not from `LLM_PROVIDER`, `LOCAL_LLM_*`, `OPENAI_MODEL`, or `AZURE_OPENAI_DEPLOYMENT` environment settings. The only supported `LLM_PROVIDER` chat override is explicit `mock` for deterministic offline tests.
Web and mobile clients may send the signed-in user, case, task, and an optional backend-approved `model_profile_id` for authorized web admin/unlimited users. They must not send provider keys, base URLs, prompts-as-routing-policy, or local budget calculations; the API resolver remains the source of truth for free local-only routing, paid external routing, EU-zone blocking, budget fallback, and audit metadata.

Routing precedence is:

1. Authorized per-session assistant selection from the web model selector. The browser sends only `model_profile_id`; the backend verifies that the user is `role=admin` or in `JURISDIGTA_UNLIMITED_ACCESS_EMAILS`, then resolves the enabled profile and provider server-side.
2. Enabled per-user override from `ai_model_user_overrides`, which applies to every task type for that user.
3. Existing group/plan/task route policy from `ai_task_route_policies`.
4. Seeded defaults created by `ApiDatabaseStore.initialize()`.

The public `GET /v1/model-routing/selectable?user_id=...&user_email=...`
endpoint returns only safe display metadata for authorized admin/unlimited
users: profile id, provider code/display name, model label, local/external
flags, EU data-zone flag, and context window. The `user_id` parameter is
preferred; `user_email` is an authenticated-browser fallback for restored web
sessions that still know the email/role but cannot provide the user id. The
backend resolves both identifiers to a stored user and applies the same
admin/unlimited eligibility checks. It does not return provider base URLs,
credentials, prompts, documents, or case content. Regular users receive
`eligible=false` and an empty profile list. Selected assistant models are
transient: they apply to the current chat session/reply/stream workflow and
reset on page reload or new case.

Seeded defaults:

- Free/default users route to `local_ollama_default`, provider `local_ollama`, model `qwen3:1.7b`. Local developer runs default to `http://127.0.0.1:11434/v1`; self-managed Docker production seeds the private Docker gateway URL so API containers can reach the host-local Ollama service.
- Admin changes to local model profiles and route policies are preserved across `ApiDatabaseStore.initialize()` runs. To change the free-account local default, add or import the Ollama model, create or edit a local profile, mark it as the default free model, then disable the previous profile only after the replacement route is enabled. If no enabled local profile matches the active free policy, routing fails closed instead of silently switching to an external model.
- `case`, `basic`, `premium`, and `unlimited` plan routes prefer `azure_foundry_gpt_4o_mini`, provider `azure_foundry`, model/deployment `gpt-4o-mini`, EU data-zone capable. Operators must set the Azure provider endpoint and encrypted credential before paid traffic can use this route.
- When a paid route policy sets `max_cost_eur` and the user's recorded cost for that plan/task reaches the cap, the resolver returns `local_budget_fallback` if `fallback_local_on_budget` is enabled and an enabled local profile is configured. If no local budget fallback is available, routing fails closed with `budget_exhausted`. Usage summaries group by provider/model/route/status/fallback reason and omit user id, subscription id, and case id from Prometheus summary labels.

The admin page lists users with paging, current providers, current profiles, direct user model assignments, route policies, user groups, local Ollama inventory, operational case reset tools, and admin audit events. `Používatelia` shows a table first and opens an Edit form for role/status changes; saves call the audited admin user endpoint and cancel returns to the table without updating data. `User model assignment` searches users by email, selects an enabled existing model profile, shows the current assigned model and effective route, and requires an admin reason for save/update/disable. `Modely a ceny` lets admins edit, enable, disable, and select the default free local profile without editing environment files. `Smerovacie politiky` choose a model by task type, plan, optional user group, local/external preference, external acknowledgement, EU data-zone requirement, fallback behavior, and priority when no per-user override is enabled. `Import z Ollama registra` starts registry pulls from a dedicated Admin menu item. `Lokálne Ollama modely` refreshes the server-local inventory when the menu item is opened, shows installed local Ollama models and configured local profiles, and matches configured profiles to installed runtime names case-insensitively to avoid duplicate rows such as `qwen3:4b` and `Qwen3:4b`. Setting a model as default uses the audited Ollama default endpoint, marks the matching local profile as the default, and rewrites default local route policies so free users use the new model. The current installed default model name is highlighted in green, its set-default action is disabled, and it cannot be disabled or removed until another local model is made default. Non-default installed models can be removed; matching local profiles are soft-deleted and any policies that still referenced them are moved to the current default before the physical Ollama remove job starts. Configured-only not-installed rows are never valid defaults, cannot be promoted, and can always be removed from the table. API payloads include model/profile identifiers and route metadata only; they do not expose provider secrets, prompts, documents, or legal case content.

Admin case reset is intentionally narrow: `GET /v1/admin/cases/users?email=...` searches users by email, `GET /v1/admin/cases/users/{user_id}/cases?include_deleted=true` returns only case id/title/status/timestamps, and `DELETE /v1/admin/cases/{case_id}` soft-deletes one selected case with a mandatory reason. This endpoint is for support/test reset operations such as freeing an expired Free-plan test account to create a fresh case. It does not hard-delete rows, expose prompts, expose uploaded/generated documents, or replace data-subject deletion and retention workflows. Public user case deletion remains subject to the normal case write-window gate.

Authorized case users can inspect this trail through:

```bash
curl -H "x-api-key: $API_KEY" \
  "$API_BASE_URL/v1/cases/$CASE_ID/ai-model-audit?user_id=$USER_ID&limit=50"
```

SQLite bootstrap is handled by `ApiDatabaseStore.initialize()`. PostgreSQL/Azure upgrades are handled by:

```bash
PYTHONPATH=src python scripts/databases/apply_api_db_schema.py
```

Minimal runnable example:

```bash
python examples/minimal_demo.py
python examples/model_routing_minimal_demo.py
```
