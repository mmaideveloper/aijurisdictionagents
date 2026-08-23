# Court decision collector

`court-decision-collector` imports Slovak `sudne rozhodnutia` (`court decisions`) into a dedicated PostgreSQL data store for MCP and internal RAG search.

The collector is separate from `laws_collector` because court decisions have different identity, update, privacy, and legal-effect semantics.

## Storage

Applied migration files are immutable because their checksums are recorded in the
database. Add schema and index changes in a new numbered migration instead of
editing an existing migration; deployment stops on a checksum mismatch.

- SQL assets: `databases/court-decision-collector/`
- Local runtime data: `runs/storage/court-decision-collector/`
- Default database backend: PostgreSQL
- Required extension for production semantic search: `pgvector`

The first schema stores:

- `court_decision_documents`: stable source identity and court metadata
- `court_decision_versions`: raw text, pseudonymized public text, checksums, metadata, and embedding vectors
- `court_decision_import_state`: restart cursor and latest processed decision
- `court_decision_update_events`: audit trail for created, updated, and unchanged imports
- `court_decision_scheduler_state`: durable UTC quota, source-count watermark, discovery checkpoint,
  and historical reconciliation cursor
- `court_decision_import_queue`: durable new-data and backfill work, retries, and completion state
- `court_decision_enrichments`: PDF provenance, processing state, complete source metadata,
  pseudonymized summary/topics, and summary embedding metadata
- `court_decision_content_chunks`: pseudonymized chunks and local embedding vectors

## On-demand PDF enrichment

Exact-decision requests use a cache-first pipeline. Only the configured InfoSud decision endpoint
and `https://obcan.justice.sk/content/public/item/` PDF URLs are accepted. The service stores the
complete source JSON, validates and atomically caches the PDF under
`runs/storage/court-decision-collector/`, extracts text with local OCR fallback, pseudonymizes it,
creates a local extractive summary/topics, chunks the content, and uses the shared local embedding
runtime. An unchanged second request is a cache hit and performs no duplicate processing.

```powershell
$env:SYSTEM_EMBEDDING_MODEL_OPTION="local"
$env:SYSTEM_EMBEDDING_MODEL="all-MiniLM-L6-v2"
.\conda\python.exe -m services.court_decision_collector `
  --enrich-source-url "https://obcan.justice.sk/pilot/api/ress-isu-service/v1/rozhodnutie/24beca89-d93b-4cfc-b664-bb28148db9da:34712443-63f4-4a0e-96fe-60bec5bc06f0"
```

Return metadata plus the pseudonymized AI-generated summary by default. Full pseudonymized text is
explicit; raw PDF/text remains controlled internal data. Broad topical search covers enriched
content only and must disclose that unprocessed PDFs may contain additional matches.

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

The console prints privacy-safe progress lines such as:

```text
court_decision_collector processing_judicial_decision reference_hash=0d64... work_class=new status=processing
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
- `jurisdigta_court_decision_imports_total{work_class="new|backfill"}`
- `jurisdigta_court_decision_imports_window{work_class="new|backfill",window="24h"}`
- `jurisdigta_court_decision_queue{work_class="new|backfill"}`
- `jurisdigta_court_decision_daily_new_quota{state="used|limit|remaining"}`
- `jurisdigta_court_decision_checkpoint_failures_total`
- `jurisdigta_court_decision_retries_total`
- `jurisdigta_court_decision_pages_without_write`
- `jurisdigta_court_decision_collector_last_activity_timestamp_seconds`
- `jurisdigta_court_decision_latest_imported_timestamp_seconds`
- `jurisdigta_court_decision_latest_imported_info`
- `jurisdigta_court_decision_latest_stored_issue_date_timestamp_seconds`
- `jurisdigta_court_decision_recent_error_info`

These metrics must remain operational and aggregate-only. Do not expose raw
decision text, source URLs, source GUIDs, ECLI values, file numbers, party
names, retrieved snippets, embeddings, prompts, or other personal/legal-risk
content in Grafana labels or tables. The latest imported decision panel may
show only a safe short name from decision form plus court type and the published
date.

## Priority scheduler and restart test

Each service cycle checks the current InfoSud source count before doing historical work. Growth beyond
the durable source-count watermark is queued as `new`, including a small overlap window for source
changes. The worker drains this queue first and commits at most 10,000 new decisions per UTC day.
Overflow remains queued with the same priority after the UTC quota rolls over. Historical reconciliation
(`backfill`) runs only while the new queue is empty and resumes from a durable page checkpoint after a
restart.

Quota usage is recorded only after the decision transaction succeeds. A retry therefore cannot consume
quota twice, and a process crash cannot silently lose queued work. A lower source count or a missing
expected page sets a degraded checkpoint status and emits an alertable counter; it is never reported as
up to date.

Run against the live source:

```powershell
.\conda\python.exe -m services.court_decision_collector --run-service --limit 25
```

For local testing, `--poll-seconds` can shorten the wait interval. Production uses `COURT_DECISIONS_WORKER_POLL_HOURS`.

Relevant configuration defaults:

```text
COURT_DECISIONS_DAILY_NEW_LIMIT=10000
COURT_DECISIONS_DISCOVERY_OVERLAP_PAGES=2
COURT_DECISIONS_BACKFILL_PAGES_PER_CYCLE=10
```

Local restart-safe fixture test:

```powershell
.\conda\python.exe -m services.court_decision_collector --run-once --fixture-source --limit 1 --stop-after-decisions 1
.\conda\python.exe -m services.court_decision_collector --run-once --fixture-source --limit 1
```

The first command stops after one committed decision. The second command resumes the durable queue and
checkpoint without rescanning from page zero. Automated tests also cover daily overflow, UTC rollover,
new-work priority over backfill, source-count regression, missing pages, and retry-safe quota accounting.

## Live source

The default source is the InfoSud API:

```text
https://obcan.justice.sk/pilot/api/ress-isu-service/v1/rozhodnutie
```

InfoSud requests use one-based page numbers even though its response metadata reports zero-based page
indexes. The client translates this boundary explicitly. The scheduler does not rely on unsupported sort
parameters or a single exact-GUID cursor: it combines a source-size watermark, overlap discovery, a
durable queue, and resumable full reconciliation.

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
- `searchCourtDecisions(query, limit, offset, published_year, year_filter_mode, court_type, court_name, sort, include_snippets, include_summaries)` searches metadata, ready pseudonymized enrichments, and pseudonymized content chunks. Conversational Slovak presentation words are removed before retrieval; purchase-contract variants and common speech-to-text spelling such as `kupón predajnej zmluve` map to the selective purchase-contract query. A count in `posledných 5` is used when `limit` is omitted. `court_name` is an exact normalized named-court filter, while `court_type` selects a generic court category. `issue_date` remains the original source value for provenance; `issue_date_normalized DATE` drives calendar sorting and year filtering. Invalid/missing dates sort last and are surfaced through data-quality metadata. Snippets and summaries are opt-in and always use public pseudonymized content.

The response includes aggregate corpus coverage and the warning that `latest` means the latest matching decisions currently available in JurisDigta. It is not a claim that the corpus contains every Slovak court decision. Legal summaries are retrieval aids, may be incomplete, and require human review before use in a legal conclusion. Logs contain only query length and filter/status metadata, never the raw question, decision text, summary, credentials, or personal data.

Migration `databases/court-decision-collector/migrations/0002_normalize_issue_date_and_court_name.sql` backfills typed dates and normalized court names. Its validation query reports parsed, invalid, and missing dates; unparseable values remain `NULL` and are never replaced with invented dates.

When InfoSud supplies `povodnySud`, that court is the issuing court used by search. The current successor court in `sud` remains preserved in the raw metadata. This prevents reorganized Kežmarok decisions (`OSKK`) currently administered by Poprad from being presented as decisions issued by Poprad (`OSPP`).
- `getCourtDecision(decision_id, full_version, outputMode)` where the default response is metadata-only. `full_version=true` returns bounded pseudonymized public text. `outputMode=internal_raw` remains restricted to controlled internal runtimes.
- `searchLegalSources(query, source_types, published_year, year_filter_mode, limit_per_source)` for protected combined metadata search across current consolidated laws and court decisions. The MCP server is model-free; clients parse natural-language questions and pass structured filters.

`outputMode=internal_raw` is reserved for controlled internal callers and is blocked unless `COURT_DECISIONS_ALLOW_INTERNAL_RAW_MCP=true` is set in that controlled runtime. Keep it disabled for normal external MCP clients.
