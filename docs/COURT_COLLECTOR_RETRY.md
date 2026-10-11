# Court metadata queue retries and source review (#869, #889)

Source 404/410, transient HTTP 408/429/5xx and transport failures schedule a
persisted `next_attempt_at` instead of aborting independent eligible work. The
first four attempts back off exponentially with bounded deterministic jitter;
after five failures missing records recheck weekly and transient records daily.
Retry-After is a lower bound. Records are never discarded or counted as imports.
Authentication, programming and storage failures still abort visibly.

Apply `databases/court-decision-collector/migrations/0005_work_retry_schedule.sql`
before rollout (store initialization also adds the column idempotently). Existing
pending work is immediately eligible. Discovery preserves retryable state and
cooldown; successful completion resets retry metadata and consumes quota once.
Scheduler pause decisions count only eligible work. Deferred new records remain
in backlog diagnostics but do not prevent independent backfill; genuine daily
quota exhaustion still pauses eligible new work. A regression test covers a
weekly deferred record alongside successful backfill without quota consumption.
To inspect deferred work, aggregate by status/last_error_type/next_attempt_at;
never export decision identifiers or bodies. Investigate source URL/availability
before operator-approved requeue. No enrichment or corpus expansion is enabled.

Validate with `python -m pytest tests/test_court_work_retry.py
tests/test_court_decision_collector.py` and run
`python examples/court_work_retry_demo.py`; the repository minimal example remains
`python examples/minimal_demo.py`. These are offline regressions, not legal
retrieval E2E evidence. Roll back application code if needed; retain the additive
column and deferred work, and expect the old worker to ignore cooldowns.

Operational logs retain only hashed references and retry categories/timestamps.
Existing retention/access policies and human review of legal-source availability
remain in force. Deployment requires the exact-commit check gate and observation
of queue progress, quotas and retry rate.

## Source investigation (2026-10-11)

A bounded read-only review found 1,160 `source_missing` queue entries, 767 pending
and 12,761 completed entries. Three missing-reference samples returned HTTP 404;
their stored listing pages and independent same-page detail controls returned
200. None appeared on its sampled page. Pagination shifts, so this establishes
record-specific failures, **not confirmed deletion**. No production disposition
was changed and no decision bodies or raw identifiers were retained.

| Hashed sample | Attempts at observation | Detail | Listing | Control | Conclusion |
| --- | ---: | ---: | ---: | ---: | --- |
| `b8550acdb5fe3ecc` | 1102 | 404 | 200 | 200 | Unresolved missing |
| `2b244ced30b5c375` | 5 | 404 | 200 | 200 | Unresolved missing |
| `f6339d9e430cfdcf` | 5 | 404 | 200 | 200 | Unresolved missing |

A public first-page control confirmed the existing `/rozhodnutie` listing and
`/rozhodnutie/{guid}` detail endpoints. The listing supplies an opaque `guid`
(the observed shape was two UUIDs joined by a colon). Do not split it, replace it
with a numeric identifier, or assume `id`/`uuid` identifies the same entity.
The collector now requires a nonempty canonical `guid`, percent-encodes reserved
path characters while preserving the colon, and verifies the detail response's
`guid` equals the requested reference. Contract mismatches abort visibly rather
than fabricate a record or silently skip source entries. Transport logs omit
exception messages because they may contain URLs or identifiers.

## Bounded diagnostics

Create an access-restricted JSON reference file under ignored `runs/` with
`source_guid`, the stored zero-based `page`, and the actual discovery `size`.
The stored page is a sample hint, never deletion evidence. Do not put raw
references into shell arguments, issue comments or tracked files.

```powershell
python -m services.court_decision_collector.source_review inspect --reference-file runs/court-source-review/reference.json
```

This read-only command sends at most three requests with a 15-second timeout per
request, TLS verification, no redirects and no transport retries. Only the
allowlisted InfoSud endpoint is permitted. It probes the original reference,
one listing page, and one canonical/control detail. A verified alias mismatch
is reported only when that listing explicitly connects `id`/`uuid` to a
canonical `guid` and the canonical detail returns the same `guid`; it does not
rewrite queue identities automatically. The output includes only a reference
hash, categories, HTTP statuses, request count and booleans. A 404, 410, empty
page, failed control or source-wide failure never automatically quarantines
anything. Do not run this command repeatedly for the same unresolved record;
keep its existing deferred schedule.

## Reviewed permanent unavailability and recovery

Apply migration `0006_source_availability_review.sql` before rollout; store
initialization also adds its schema idempotently. It adds `source_unavailable`
and `last_http_status` without changing queue statuses, existing cooldowns or
attempt counts, plus a minimized append-only application audit trail in
`court_decision_availability_reviews`. Existing rows stay eligible/deferred;
their HTTP status remains unknown until the next normally scheduled response.
There is no bulk inference from historical `source_missing` rows.

Quarantine requires a stored 404/410 detail response and explicit human review
of the canonical identity, working endpoint/control and corroborating source
withdrawal or unavailability evidence. A first 404 alone is insufficient. Pause
the collector during operator changes to avoid a request already in flight.
Keep restricted evidence outside the database and provide its SHA-256 digest
plus a digest of the authorized reviewer reference. Hashing is data minimization,
not anonymization; access restrictions still apply. Categories are fixed enums.

```powershell
python -m services.court_decision_collector.source_review quarantine --reference-file runs/court-source-review/reference.json --evidence-category source_withdrawal --evidence-sha256 <64-lowercase-hex> --reviewer-sha256 <64-lowercase-hex> --confirm-permanent-unavailability
python -m services.court_decision_collector.source_review requeue --reference-file runs/court-source-review/reference.json --evidence-category operator_requeue --evidence-sha256 <64-lowercase-hex> --reviewer-sha256 <64-lowercase-hex>
```

`operator_verified_unavailable` is the other quarantine category;
`verified_source_change` is the other recovery category. These commands require
authorized database access through existing runtime configuration and perform
no automatic migration, live probe or deployment. Requeue applies only to a
previously quarantined record, resets its retry budget/cooldown and is audited.
Repeated identical dispositions do not create duplicate audit events.

Quarantined records remain retained and never receive automatic detail requests,
including after restart or unchanged rediscovery. They consume no quota and do
not block valid work. Ordinary unresolved/transient failures retain their existing
deferred retry schedules and Retry-After behavior. Successful completion clears
HTTP/retry metadata and counts quota once. Stale completion/retry operations
cannot undo a reviewed disposition. This collector-only state does not delete
existing corpus content or change API/MCP legal retrieval contracts.

Aggregate operational visibility without exporting identifiers:

```sql
SELECT source_unavailable, status, last_error_type, last_http_status,
       COUNT(*) AS records, MIN(next_attempt_at) AS next_attempt
FROM court_decision_import_queue
GROUP BY source_unavailable, status, last_error_type, last_http_status;
```

Apply the existing operational retention/deletion policy to restricted reference
files and review evidence. Remove reference files after the investigation;
retain only approved minimized audit evidence. On source-data deletion, include
review rows matched by `source_system` and SHA-256 of the source reference in
the authorized deletion transaction. Do not infer a legal conclusion from
unavailability, bypass consent, or relax human review of legal outputs.

## Validation and rollback

Store typing gate (#894): run `python -m mypy src/services/court_decision_collector
--follow-imports=silent` and `python -m ruff check src/services/court_decision_collector`.
Numeric PostgreSQL rank/count values are converted explicitly; a missing aggregate
row fails visibly instead of fabricating corpus coverage. Valid search scores,
counts and dates are unchanged. The `--postgres` demo also validates typed empty
synthetic corpus coverage. Run `python -m pytest tests/test_court_store_types.py`
for aggregate count/date and missing-row regressions. The default repository
example remains `python examples/minimal_demo.py`.

```powershell
python -m pytest tests/test_court_work_retry.py tests/test_court_source_review.py tests/test_court_source_availability_postgres.py tests/test_court_decision_collector.py tests/test_court_decision_enrichment.py
python examples/court_work_retry_demo.py
python examples/court_work_retry_demo.py --postgres
```

The PostgreSQL tests create and remove unique synthetic databases using the
existing `COURT_DECISIONS_DB_CLOUD` setting (or documented synthetic local
defaults), refuse non-loopback connections and skip with validation pending
when local PostgreSQL is unavailable. The PostgreSQL demo requires the existing
loopback court configuration and removes its synthetic database in `finally`.
Both require local `CREATEDB` privileges and isolate pgvector per database;
they never copy existing local/production records.
The default demo is deterministic/offline; `python examples/minimal_demo.py`
remains the repository minimal example. These are collector integration checks,
not frontend/API/MCP real-model E2E acceptance; no retrieval behavior is changed.

Retain additive schema on rollback. A pre-#889 worker ignores `source_unavailable`,
so **keep that worker stopped if reviewed exclusions must remain effective**.
Do not resume an old worker until exclusions have been safely reviewed/requeued
or a compatible version restored. No new environment keys or GitHub Environment
inputs are introduced. Production deployment remains subject to the successful
exact-commit build gate and separate release authorization.
