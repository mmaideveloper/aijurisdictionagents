# Flow Packs API (Slovak legal process packs)

This API adds flow-pack lifecycle management for Slovak legal processes.

## Purpose

Flow packs provide configurable process metadata used by a future process router:

- intake requirements (`required_facts`)
- required outputs/documents
- proactive recommendations
- escalation guidance
- enabled/disabled runtime state
- immutable version history

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

## Soft delete and versioning behavior

- `DELETE` marks `is_deleted=true`, sets `deleted_at`, and forces `is_enabled=false`.
- lifecycle is `draft -> published -> retired`; a retired version cannot be republished.
- only draft versions are editable. Enabling publishes a version permanently and published
  content is immutable; changes require a derived draft with a new version.
- mutation endpoints require authenticated admin authorization in addition to `x-api-key`.
- version values are immutable and unique per `flow_key`.
- uniqueness is country-scoped: `(jurisdiction, flow_key, version)`.
- creating a new version never mutates prior versions.

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
Assignment validation rejects disabled, deleted, draft, incompatible, or unregistered graph/flow combinations.
See `docs/LANGGRAPH_CASE_ORCHESTRATION.md`.
