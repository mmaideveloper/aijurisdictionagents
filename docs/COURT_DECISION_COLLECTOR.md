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
court_decision_collector processing_judicial_decision source_guid=fixture-sk-decision-1 number=12C/34/2024 year=2024 status=processing court=Okresny sud Bratislava I label=ECLI:SK:OSBA1:2024:1234567890.1
```

The same progress lines are appended to `logs/court-decision-collector.log` by default.

## Grafana monitoring

Self-managed production provisions a separate Grafana dashboard named
`JurisDigta Court Decision Service`.

The dashboard uses aggregate Prometheus metrics from
`scripts/server/export_system_status_metrics.py`:

- `max without(status) (last_over_time(jurisdigta_component_status{component="court_decision_collector"}[15m]))`
- `jurisdigta_court_decisions_total`
- `jurisdigta_court_decision_versions_total`
- `jurisdigta_court_decision_versions_with_embeddings_total`
- `jurisdigta_court_decision_collector_events_total`
- `jurisdigta_court_decision_collector_last_activity_timestamp_seconds`
- `jurisdigta_court_decision_latest_imported_timestamp_seconds`
- `jurisdigta_court_decision_latest_stored_issue_date_timestamp_seconds`
- `jurisdigta_court_decision_recent_error_info`

These metrics must remain operational and aggregate-only. Do not expose raw
decision text, source URLs, source GUIDs, ECLI values, file numbers, party
names, retrieved snippets, embeddings, prompts, or other personal/legal-risk
content in Grafana labels or tables.

## Service loop and restart test

The production-style service polls decision pages, saves a `live_loop` cursor after each processed decision, and waits for the next poll when the source returns no more decisions. It does not exit on `status=up_to_date`.

Run against the live source:

```powershell
.\conda\python.exe -m services.court_decision_collector --run-service --limit 25
```

For local testing, `--poll-seconds` can shorten the wait interval. Production uses `COURT_DECISIONS_WORKER_POLL_HOURS`.

Local restart-safe fixture test:

```powershell
.\conda\python.exe -m services.court_decision_collector --run-once --fixture-source --limit 1 --stop-after-decisions 1
.\conda\python.exe -m services.court_decision_collector --run-once --fixture-source --limit 1
```

The first command stops after one judicial decision with `status=stopped_mid_run`. The second command resumes from the saved `live_loop` cursor, processes the remaining fixture decisions, and then stops with `status=up_to_date`.

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

### Source timeout diagnostics

Production defaults to a 90 second InfoSud request timeout with 3 attempts and a
5 second retry backoff:

```text
COURT_DECISIONS_SOURCE_TIMEOUT_SECONDS=90
COURT_DECISIONS_SOURCE_RETRY_ATTEMPTS=3
COURT_DECISIONS_SOURCE_RETRY_BACKOFF_SECONDS=5
```

Retry logs include only safe request context such as `stage=list_decisions
page=5362 size=25` or `stage=get_decision guid_hash=...`. They must not log raw
decision text, source URLs, full source GUIDs, party names, prompts, snippets,
or embeddings.

Use this exact request test from `jurisdigta-server` when diagnosing upstream
timeouts:

```bash
curl -k --connect-timeout 20 --max-time 90 \
  -w '\nhttp=%{http_code} connect=%{time_connect}s tls=%{time_appconnect}s starttransfer=%{time_starttransfer}s total=%{time_total}s\n' \
  'https://obcan.justice.sk/pilot/api/ress-isu-service/v1/rozhodnutie?page=5362&size=25' \
  -o /tmp/infosud-page-5362.json
```

Run the detail endpoint only with an operationally necessary source GUID, and
avoid pasting raw decision bodies into tickets or logs.

## MCP tools

The MCP server exposes:

- `getVersion()` includes court-decision collector version, status, latest imported decision/source GUID, and latest import time.
- `getStatistics(country_code)` includes court-decision collector version, total court decisions, published decisions, total versions, latest imported decision/source GUID, latest import time, court metadata, ECLI/file number, issue date, and collector cursor status.
- `searchCourtDecisions(query, limit)` for pseudonymized metadata/snippet search.
- `getCourtDecision(decision_id, outputMode)` where `outputMode=public` is the default and returns pseudonymized text.

`outputMode=internal_raw` is reserved for controlled internal callers and is blocked unless `COURT_DECISIONS_ALLOW_INTERNAL_RAW_MCP=true` is set in that controlled runtime. Keep it disabled for normal external MCP clients.
