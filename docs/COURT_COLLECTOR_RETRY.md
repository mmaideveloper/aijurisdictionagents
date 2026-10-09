# Court metadata queue retries (#869)

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
