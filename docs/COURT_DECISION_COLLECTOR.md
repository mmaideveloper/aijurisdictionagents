# Court decision collector

`court-decision-collector` imports Slovak `sudne rozhodnutia` (`court decisions`) into a dedicated PostgreSQL data store for MCP and internal RAG search.

The collector is separate from `laws_collector` because court decisions have different identity, update, privacy, and legal-effect semantics.

## Storage

- SQL assets: `databases/court-decision-collector/`
- Local runtime data: `runs/storage/court-decision-collector/`
- Default database backend: PostgreSQL
- Required extension for production semantic search: `pgvector`

The first schema stores:

- `court_decision_documents`: stable source identity and court metadata
- `court_decision_versions`: raw text, pseudonymized public text, checksums, metadata, and embedding vectors
- `court_decision_import_state`: restart cursor and latest processed decision
- `court_decision_update_events`: audit trail for created, updated, and unchanged imports

## Privacy and legal-risk controls

Court decisions may include personal data. Raw text is retained only for controlled internal provenance and audit use. MCP/user-facing output uses pseudonymized text by default. External model routes must not receive raw decision text unless a later compliance review approves a different policy.

Local JurisDigta model routes may use raw context only inside the controlled runtime, and logs must not include raw decision bodies, personal identifiers, prompts, or full retrieved context.

## Local fixture run

Set a dedicated database URL:

```powershell
$env:COURT_DECISIONS_DB_BACKEND="postgres"
$env:COURT_DECISIONS_DB_CLOUD="postgresql://postgres:postgres@127.0.0.1:5432/court_decisions_sk"
.\conda\python.exe -m services.court_decision_collector --fixture
```

The console prints progress lines such as:

```text
court_decision_collector processing_decision source_guid=fixture-sk-decision-1 court=Okresny sud Bratislava I label=ECLI:SK:OSBA1:2024:1234567890.1
```

## Live source

The default source is the InfoSud API:

```text
https://obcan.justice.sk/pilot/api/ress-isu-service/v1/rozhodnutie
```

Run a small live page:

```powershell
$env:COURT_DECISIONS_IMPORT_LIMIT="5"
.\conda\python.exe -m services.court_decision_collector --live --page 0
```

## MCP tools

The MCP server exposes:

- `searchCourtDecisions(query, limit)` for pseudonymized metadata/snippet search.
- `getCourtDecision(decision_id, outputMode)` where `outputMode=public` is the default and returns pseudonymized text.

`outputMode=internal_raw` is reserved for controlled internal callers and is blocked unless `COURT_DECISIONS_ALLOW_INTERNAL_RAW_MCP=true` is set in that controlled runtime. Keep it disabled for normal external MCP clients.
