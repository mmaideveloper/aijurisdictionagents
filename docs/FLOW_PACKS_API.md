# Flow Packs API (Slovak legal process packs)

This API adds versioned flow-pack lifecycle management and isolated offline evaluation for legal processes.

## Purpose

Flow packs provide configurable process metadata used by a future process router:

- intake requirements (`required_facts`)
- required outputs/documents
- proactive recommendations
- escalation guidance
- enabled/disabled runtime state
- immutable version history
- versioned routing metadata: question kind, legal domain, requested outcome, positive/negative examples, and clarification policy
- immutable SHA-256 definition pins used by evaluation and approval

Default seeded Slovak packs include:

- `sk.contract.sale_purchase`
- `sk.company.registry_change`
- `sk.company.owner_transfer`
- `sk.civil.lease_advisory`
- `sk.probate.inheritance_proceeding`
- `sk.civil.power_of_attorney`
- `sk.civil.payment_confirmation`
- `sk.criminal.criminal_complaint`
- `sk.notary.notarial_process`
- `sk.support.person_company_screening`

The Slovak screening pack now advertises `dovera_debtor_check` alongside the existing screening tools so debt-risk checks can include normalized Dôvera debtor-list evidence.

## Storage

Runtime data uses SQLite under repository runtime storage:

- default: `runs/storage/api/sqlite/flow_packs.sqlite3`
- override env: `API_FLOW_PACKS_SQLITE_PATH`
- when `DB_OPTION=postgres|azure`, flow packs use `DB_CLOUD` PostgreSQL connection (same API DB backend selection rules)

SQL asset for schema:

- `databases/api/flow_packs_schema.sql`
- chat-simulator seed additions: `databases/api/seeds/001_chat_simulator_flow_packs.sql`
- country separation is modeled in the same `flow_packs` table via `jurisdiction` (no separate table per country)
- seed SQL is idempotent (`WHERE NOT EXISTS`) so existing rows are not overridden and duplicates are not created.

## Endpoints

All endpoints require `x-api-key`.

- `GET /v1/flow-packs?include_deleted=false`
  - list flow packs (latest and historical versions, ordered by key/version)
  - optional filter: `jurisdiction=SK|CZ|...`
- `GET /v1/flow-packs/{flow_key}/versions?include_deleted=true`
  - list versions for one flow key
  - optional filter: `jurisdiction=SK|CZ|...`
- `GET /v1/flow-packs/{flow_key}/versions/{version}`
  - fetch a single version
  - when the same `flow_key+version` exists for multiple countries, pass `jurisdiction`
- `POST /v1/flow-packs`
  - create a flow pack version (if `version` omitted, auto-increment for key)
- `POST /v1/flow-packs/{flow_key}/versions`
  - create next version derived from latest version
  - optional query: `jurisdiction=SK|CZ|...` (recommended in multi-country setups)
- `PATCH /v1/flow-packs/{flow_key}/versions/{version}`
  - update metadata/definition for a version
  - optional query: `jurisdiction=SK|CZ|...` (required if ambiguous)
- `POST /v1/flow-packs/{flow_key}/versions/{version}/enable`
- `POST /v1/flow-packs/{flow_key}/versions/{version}/disable`
- `DELETE /v1/flow-packs/{flow_key}/versions/{version}`
  - soft delete (also disables the version)
  - optional query: `jurisdiction=SK|CZ|...` (required if ambiguous)

## Lifecycle and publication gates

- `DELETE` marks `is_deleted=true`, sets `deleted_at`, and forces `is_enabled=false`.
- lifecycle is `draft -> test_ready -> testing -> test_passed -> production_approved -> published -> retired`.
- new admin versions always start disabled in `draft`; `is_enabled=true` is rejected and cannot bypass evaluation.
- only drafts are editable. `POST .../lock-for-testing` validates required routing content, records the
  admin/reason/time, creates the canonical definition hash, and makes that version immutable.
- `/enable` accepts only `production_approved`; `/disable` accepts only `published`. Retired versions
  cannot be republished. Changes always require a new draft version.
- bundled defaults use a private trusted-seed path; that path is unavailable through the admin API.
- mutation endpoints require authenticated admin authorization in addition to `x-api-key`.
- version values are immutable and unique per `flow_key`.
- uniqueness is country-scoped: `(jurisdiction, flow_key, version)`.
- creating a new version never mutates prior versions.

## Offline evaluation API

All evaluation endpoints require API and AI-model-admin authorization.

- `POST /v1/flow-evaluations/suites` creates an immutable, synthetic-only suite. The request must
  explicitly confirm synthetic data, chooses `routing_only` or `full_graph` per case, sets a routing
  accuracy threshold, and sets retention from 1 to 30 days.
- `GET /v1/flow-evaluations/suites/{suite_id}` returns suite pins and counts, not synthetic question text.
- `POST /v1/flow-evaluations/runs` records one complete suite-mode observation set and evaluates hard gates.
- `GET /v1/flow-evaluations/runs/{run_id}` returns minimized metrics and pinned provenance.
- `POST /v1/flow-evaluations/flows/{flow_key}/versions/{version}/production-approval?jurisdiction=SK`
  records human approval of the latest successful, non-stale run and atomically advances the lifecycle.
- `DELETE /v1/flow-evaluations/expired` applies run/result retention deletion.

Runs pin flow ID/version/hash, suite version/hash, graph version, routing-policy hash, provider/model route,
and a synthetic run ID. Hard gates cover routing threshold, schema/policy, required citations and provenance,
zero privacy violations, no unsupported automatic finalization, and required human review. Failed or stale
runs cannot be approved. Evaluation never reads or changes production case-flow assignments or user sessions.
Stored results omit prompts, generated response text, source bodies, credentials, and personal facts.
The migration also creates immutable promotion-provenance storage (approval, prior/target assignment hash,
actor, time, and rollback link) for the separate production assignment workflow.

## Admin authoring and offline test workspace

The frontend route `/app/admin/ai-models` includes a **Flow packages** workspace for server-authorized
administrators. It can search and filter version history by jurisdiction, domain, question kind,
requested outcome, lifecycle, and registered-graph compatibility. Administrators can clone any version
into a new draft, edit the structured routing fields or validated JSON, compare it with the prior version,
validate it, and lock it for testing. Locked versions are read-only and must be cloned before changing them.

Offline evaluation remains separate from production assignment. The workspace creates or loads an immutable
synthetic suite, records the selected graph, routing policy, provider/model route, and sanitized observations,
and displays the server-evaluated gates. A human-review confirmation is mandatory before submission. The UI
does not expose production approval or assignment; that is a separate audited workflow. In the existing case
assignment screen, only enabled versions whose lifecycle is exactly `published` are labelled and offered as
published flow packages.

The evaluation API intentionally has no suite-list endpoint yet. An administrator creates a suite in the
workspace or loads a known immutable suite ID. Test inputs must be synthetic and minimized: do not paste
customer case content, credentials, source bodies, model prompts/responses, or hidden reasoning into suite or
observation JSON. Run summaries retain only hashes, identifiers, metrics, gates, and the configured expiry.

Minimal frontend regression:

```powershell
cd frontend/aijurisdictionfronend
npm test -- --run src/__tests__/adminFlowPackages.test.tsx src/__tests__/aiModelAdminCaseCatalog.test.tsx
```

## Runtime warning on unmatched requests

During chat reply processing, the API now attempts to match each user request against enabled flow packs
for the session country. If no flow pack matches, the API logs a warning (`No flow-pack matched user request`)
with session id, country, and a short request excerpt.

For chat-simulator coverage, flow definitions now include:

- `steps`: ordered process stages each testcase flow follows.
- `delivery`: output packaging contract:
  - one output -> `single_document`
  - multiple outputs -> `multi_document_bundle = "zip"`

## Minimal runnable example

```bash
python examples/flow_packs_minimal_demo.py
```

```bash
python examples/flow_evaluation_minimal_demo.py
```

```bash
python examples/chat_simulator_flowpack_coverage_demo.py
```

Repository default smoke demo remains available:

```bash
python examples/minimal_demo.py
```

Executable case packs additionally declare required/conditional facts, MCP query/failure policy,
prompt references, templates, allowlisted tools, consent purpose, validation gates, escalation,
and human oversight. For `legal_document_workflow@2`, `mcp_retrieval` must include
`schema_version`, a stable `policy_id`, `case_type_keys`, `jurisdictions`, a reviewed `default_query`,
bounded `search_limit`/`text_limit`, and optional `fact_query_mappings`. Fact mappings recognize
only reviewed aliases and select one reviewed search query; they never append raw fact values.
For `legal_document_workflow@3`, the immutable flow must also provide `tool_policy` schema version 1.
Each allowlisted entry binds a registered tool name to its purpose, provider, required verified
fact keys, input mapping, permitted data fields, jurisdiction, bounded timeout, consent scope, and
consent-text version. The LLM sees only eligible definitions and can propose at most one tool;
execution still requires an exact per-run ledger grant.
For `legal_document_workflow@4`, the flow must additionally provide `presentation_policy` schema
version 1. It assigns reviewed renderer IDs and versions, a default renderer, allowed explicit user
overrides, and bounded item/string/payload limits. Assignment validation rejects unknown renderers,
missing text fallback, duplicate entries, and unsafe bounds before activation. A model can propose
only a flow-assigned renderer compatible with the result shape; deterministic policy makes the
decision. HTML is represented by a trusted `result_card`, never arbitrary markup.
Assignment validation rejects disabled, deleted, draft, incompatible, or unregistered graph/flow combinations.
The mandatory primary LangGraph router automatically discovers active
dedicated assignments backed by enabled, published versions. No separate production case-type
allowlist must be synchronized with the registry.
See `docs/LANGGRAPH_CASE_ORCHESTRATION.md`.
