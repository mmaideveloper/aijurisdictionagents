# LangGraph case orchestration

JurisDigta uses a registered, versioned LangGraph runtime for guided legal cases. The first
active reference is `sk.civil.payment_confirmation@3` on
`legal_document_workflow@2`; all other enabled Slovak case types receive an explicit
`unsupported_or_human_review@1` assignment until their legal configuration is reviewed.

## Runtime contract

Each run pins `case_type_key`, `graph_key@version`, and immutable `flow_key@version`. Assignment
changes apply only to new runs. Python graph code is selected only from the reviewed registry in
`app/case_workflows/registry.py`; administrators cannot submit executable code, arbitrary nodes,
or transitions.

The legal-document graph routes and pins configuration, validates facts, interrupts for one
missing fact at a time, retrieves current requirements through JurisDigta MCP, executes only consented
allowlisted tools, blocks conflicts, drafts, runs output and GDPR/safety checks, performs final
case review, and completes or escalates. MCP/model/tool failures remain visible and cannot become
fabricated success. `LANGGRAPH_STRICT_MSGPACK=true` prevents permissive checkpoint serialization.

Graph v2 performs required-fact validation before retrieval. Its immutable flow policy supplies a
reviewed `policy_id`, allowed case types and jurisdictions, bounded MCP limits, a reviewed default
query, and optional mappings from verified fact aliases to reviewed legal-search queries. Raw fact values are
never appended to the query. Unknown or instruction-like values are omitted, and an invalid policy
blocks the run. Audit events record the policy identifier, source IDs, and matched-fact count—not the
query or personal facts. Graph v1 remains registered only so existing pinned runs can resume.

PostgreSQL production checkpoints use `PostgresSaver`; local deterministic tests use
`InMemorySaver`. Run metadata and append-only sanitized audit events are stored in the API
database by migration `0020_langgraph_case_workflows.sql`. Runtime database files remain under
`runs/storage/api/`, never under `databases/`.

## API and channels

- `GET /v1/case-workflows/graphs` lists reviewed graph versions.
- `GET /v1/case-workflows/assignments` lists active and historical assignments.
- Admin-only `POST /assignments/validate` validates graph, case type, flow lifecycle, schema, and
  compatibility.
- Admin-only `POST /assignments` requires explicit `confirmation=true` when replacing a default.
- `POST /runs`, `POST /runs/{id}/resume`, `GET /runs/{id}`, and `GET /runs/{id}/events` expose the
  shared web/mobile/chat-simulator workflow state.

The existing chat API invokes the same runtime when `AI_CASE_ORCHESTRATION_MODE=active` and the
selected case type is in `AI_CASE_ORCHESTRATION_CASE_TYPES`. `legacy` is the rollback setting.
Legal-research messages do not enter the document workflow and retain the established MCP path,
including when the user says they "want to know" the latest law inside an existing document case.
The runtime leaves any waiting case workflow unchanged while answering the standalone research
question. Document orchestration still takes precedence when the same message explicitly asks to
prepare, create, revise, or export an artifact such as a document, contract, draft, or PDF.

For the real local regression, `scripts/prepare_issue_713_latest_law_e2e.py` seeds only isolated
synthetic PostgreSQL records and writes the expected MCP source ID to an ignored manifest under
`runs/e2e/issue-713-latest-law/`. Retain its sanitized manifest and final screenshot for at most
seven days.

## GDPR and EU AI Act controls

State is user/case scoped. Events contain identifiers, counts, decisions, model/tool route
metadata, and source IDs—not prompts, credentials, or unnecessary personal facts. Personal-data
tools are disabled until the consent-purpose implementation in task #389 is available. Adverse or
ambiguous screening, missing evidence, conflicts, failed validators, and unsupported case types
require human review. Outputs disclose AI assistance and the need for human review.
If model prose omits a user-verified value, the workflow appends that exact value in a labeled
verified-data section before validation. It never infers or fills an absent value.

Case deletion removes associated workflow run state, audit events, and checkpoints with the
parent case. Keep the active allowlist limited to reviewed flows; widening it requires the same
privacy, legal, and real-path E2E review used for the payment-confirmation reference flow.

## Operations and rollback

Production deploy selects `active` or `legacy` explicitly. Roll back by dispatching the exact
validated commit with `case_orchestration_mode=legacy`; never change a running case's pinned
versions. A retired flow version cannot be republished, and a published version cannot be edited.

Deployments can contain the legacy `sk.civil.payment_confirmation@1` definition created before
the MCP retrieval policy became mandatory and the compatible `@2` definition with query keys.
Startup preserves both published versions, seeds policy-driven `@3`, and upgrades only the active
system-seeded assignment for new cases to graph v2/flow v3. Existing workflow runs remain pinned
to their original graph and flow versions, while administrator-created assignments are not
silently replaced.

Run the deterministic example:

```powershell
python examples/langgraph_case_workflow_demo.py
```

Final acceptance additionally requires the real local frontend → API → MCP → PostgreSQL → Azure
Foundry E2E and its PDF, first-page render, screenshot, and sanitized manifest.
Prepare its synthetic records only after the API and laws schemas are applied to dedicated local
databases. The preparation command requires `DB_OPTION=postgres`, loopback `DB_CLOUD`,
`LAWS_DB_BACKEND=postgres`, and a loopback `LAWS_DB_CLOUD` database whose name contains `e2e`:

```powershell
python scripts/prepare_issue_635_langgraph_e2e.py
```

The script refuses non-loopback or non-E2E law databases, upserts only the synthetic
`issue-635-civil-code` source, and writes ignored evidence under `runs/e2e/issue-635-langgraph/`.
