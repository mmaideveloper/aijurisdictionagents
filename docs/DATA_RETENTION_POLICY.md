# Retention policy and execution (#389)

Status: technical controls implemented; five category periods approved by the repository owner on 2026-10-15.
Owner: Esolutions SK s.r.o. privacy/legal owner; operations executes approved policy.

`config/privacy_retention.json` records the owner's 2026-10-15 instruction: 30 days for
completed/deleted cases, closed accounts, consent evidence and backups. The approval
reference is the instruction in the deployment chat. This approves these configured
periods; it does not certify GDPR compliance or expand the erasure worker's capabilities.
Active cases, legal holds and statutory accounting exceptions continue to apply.

| Category | Current rule | Execution / owner |
| --- | --- | --- |
| Active account | Account lifetime; no blanket consent as contractual lawful basis | Privacy owner reviews closure |
| Completed/deleted cases, messages, uploads, generated files, review proposals | 30 days after case update; never purge an active case or a subject on legal hold | Retention worker, FK cascades, workflow deletion, file cleanup queue |
| Closed accounts | 30 days after closure; DSAR workflow can deidentify and disable account earlier | Operator-reviewed request; statutory exceptions assessed separately |
| Consent evidence | 30 days for closed/erased subjects, subject to lawful holds; do not discard the current live-account consent decision | Privacy owner; DSAR removes subject-linked decisions after review |
| Compliance events | Content-free, no subject identifiers; append-only | No automatic deletion configured; owner must approve an evidence period before release |
| Diagnostic traces, logs, telemetry | Existing seven-day diagnostic/telemetry policy | Workflow expiry worker, Loki and Azure table retention; operations verifies each backend |
| Subscriptions, invoices, billing totals | Statutory obligations; generally ten years for accounting records under existing privacy notice | Accounting/privacy owner; excluded from blanket purge |
| Backups | 30 days | Backup owner verifies snapshot expiry and restore suppression |
| Test evidence | At most seven days, synthetic only | Ignored `artifacts/` or `runs/`; follow E2E evidence rule |

## Runnable job

Run from the repository with the profile verified and the local conda runtime activated:

```powershell
.\conda\python.exe scripts/run_privacy_retention.py
.\conda\python.exe scripts/run_privacy_retention.py --policy config/privacy_retention.json --execute
```

The first command reports counts only. The second refuses an unapproved policy. The
approved completed/deleted case TTLs are positive integer days; expiry uses the
case update timestamp. It excludes active cases and legal holds, removes workflow traces
and checkpoints, deletes case rows and derived data, and queues file deletion in the same
transaction as core row deletion. Local file cleanup is idempotent, confined to the configured
blob root, and does not delete a file still referenced by another document/communication.
Failures remain queued. Remote storage requires its own operator adapter and is reported
pending rather than falsely erased. Stop/restart live workers around destructive execution;
the standalone job cannot evict another process's in-memory session/checkpoint state.

Only completed/deleted case expiry is automated by this new job. Account, consent,
accounting, observability and backup periods are documented owner workflows, not implemented
as arbitrary filesystem purges. Existing diagnostic expiry remains authoritative. Do not
enable production cleanup or claim complete repository-wide retention enforcement until
the manual setup checklist and external backend validation have been completed.

## Restore suppression

Keep reviewed deletion-request IDs and their subject tombstones in restricted operational
storage for the approved backup lifetime. Before exposing a restored backup to services,
reapply approved restrictions/erasures and queued artifact deletion. Never allow a restore
to revive withdrawn consent. A backup is not declared deleted merely because its live row
was deleted; record snapshot expiry or approved cryptographic erasure evidence separately.

## Approval and rollback

The owner supplied the five 30-day periods on 2026-10-15. Privacy/operations continue to
apply statutory exceptions, hold criteria and restore suppression. Operations deploys the
reviewed policy and runs a dry run before enabling a daily
timer. Disable the timer or restore the prior policy to halt future cleanup. Purged data cannot
be recovered through a feature flag; recovery requires an approved backup restore with the
suppression ledger reapplied. Policy approval is separate from engineering/test acceptance.
