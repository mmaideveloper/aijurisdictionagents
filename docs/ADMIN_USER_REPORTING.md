# Admin Grafana user reporting (#806, #815)

The private **JurisDigta Admin Users and Performance** dashboard extends the existing
Application Performance dashboard. Preview with
`python Deployment/monitoring/user_reporting.py --preview`.
PostgreSQL migrations `806_admin_user_reporting.sql` and `815_admin_user_statistics.sql`
install its reporting contract. The private organization's home dashboard is set during provisioning.
Shared Grafana provisioning never contains the reporting data source or user IDs.

## Definitions and limits

- Total counts retained accounts registered before the selected range end, including
  disabled accounts, minus explicit service, synthetic, deleted or restricted exclusions.
  Select the next midnight in Europe/Bratislava to include an entire particular day.
  The range start does not affect this cumulative count. Accounts
  have no native deletion flag: use `admin_reporting.excluded_users` for soft deletion
  and restriction, or actually delete the account. Never infer type from email.
- Registrations group retained eligible accounts by Europe/Bratislava calendar date.
  Range edges can be partial days. Account removal also changes historical counts.
- Daily active users create a case or submit a question recorded in the usage ledger.
  Deterministic replies count; reading/downloading, polling, token refresh and
  background ledger rows without question_id do not. INSERT triggers retain only
  user/day facts. All channels using those paths share the definition; no backfill.
- Activity uses whole selected calendar days (today so far), even for sub-day edges.
  Dates before the first complete collection day, outside retention or in the future
  return null. Zero means a covered day without qualifying events. See coverage panel.
- Latest 10 means eligible registrations within the range, newest first, ties ordered
  by ID, displaying email and registration time only to reporting administrators.
- Top 10 token consumers means users with ledger usage in the selected range, sorted
  by total tokens descending, ties by internal ID. Active accounts show email.
  Soft-deleted and observed hard-deleted accounts show `Deleted user (deleted)` and
  their token totals, never email or their internal identifier. Different deleted
  users remain separate rows even though their display labels are identical.
  Historical orphans that cannot be proven deleted remain unattributed; no history
  is invented. A deletion marker stores only existing ledger user ID and eligibility,
  not an email or token copy. Markers disappear when the user's final ledger row is
  deleted, anonymized, or the ledger is truncated. Daily pruning also removes stale markers.
  Restricted/service/synthetic accounts remain excluded even after hard deletion.
- Tokens group each usage_id once across providers/models/statuses in the half-open
  request_completed_at range [from,to). Cached input is already part of input.
  Stored total is not increased by cached tokens. Separate billable retries remain
  separate entries. The ledger has no provider request ID for deduplicating erroneous
  duplicate usage IDs; the report does not silently guess which requests are repeats.
- Estimated entries have token_counting beginning with `estimated`; unspecified
  entries have neither that marker nor `provider_reported`. Existing chat entries
  use character estimates, including some deterministic replies. This is recorded
  ledger usage, not a billing statement. Unspecified counts are not presented as exact.
- The table includes zero-usage users, all selectable pages of 100, ID/token ordering,
  and total_rows. Reconciliation separates eligible/deleted/excluded/unattributed totals
  without exposing excluded/orphaned identifiers.

Default range: 30 days. Non-finite, empty, reversed or over-366-day ranges and invalid
pagination fail. Refresh: 1 minute. Read-login timeout: 10s; connection limit: 3.
Malformed source timestamps/metadata cause errors, never zeros. Grafana distinguishes
failed queries, empty results and null/unavailable values.

## Privacy and operations

Purpose: internal account adoption and recorded resource usage. User IDs remain
personal data. Before rollout the privacy owner records the processing basis and
confirms privacy-notice coverage; a new consent checkbox is not assumed appropriate.
Email is read live only for retained eligible accounts in the two private top-10
tables. No names, prompts, case facts or credentials enter reports. There is no AI
assessment/automated decision about users; existing human oversight is unchanged.

[Grafana OSS organization members can query every data source](https://grafana.com/docs/grafana/latest/datasources/).
Use a dedicated organization containing only authorized reporting administrators.
Disable anonymous access, automatic membership/role sync, query caching, snapshots
and public sharing. Folder hiding is insufficient. Provisioning refuses organization
1 and non-Admin members. Server admins remain trusted. Review membership changes;
the installer is not a continuous membership-policy enforcer.

The database login gets EXECUTE on named SECURITY DEFINER functions with fixed
search_path, no raw table privileges or role memberships. Ownership stays with the
trusted migration owner. Apply the access SQL in one transaction; it rejects direct
table privileges including PUBLIC grants. Require TLS and restrict ingress to Grafana.

Activity retains 90 calendar days including today and cascades on account deletion.
Exclusions disappear from identified results immediately. Pruning physically removes
expired/excluded activity on writes; also schedule a daily prune for idle periods.
Account/ledger retention follows existing policy; no payload copies are created.
Deletion does not extend ledger retention. If an erasure requires removal/anonymization
of the ledger itself, the corresponding ranking disappears too. This report is not
an exception to erasure/restriction obligations. Delete markers cannot be used to
recover an email. Account IDs must never be reused for a different account.
Include this schema in backup expiry/restore deletion procedures. No cached query
results or unapproved exports; browser state clears on logout/close.

Access logs must record authenticated actor, organization, action/path, time, result
and correlation ID without request/response bodies, SQL text, user-ID rows or secrets.
Verify gateway/session audit coverage before production rollout.

## Verification

For #815 use an isolated local PostgreSQL container `juris-issue815-postgres`, bound
to `127.0.0.1:5815`, with runtime data mounted from `runs/storage/issue815/postgres/data`.
Create `issue815_reporting_tests`, set process-only `DB_OPTION=postgres` and `DB_CLOUD`
to that loopback database, then run `python scripts/databases/apply_api_db_schema.py`.
The fixture applies the reporting contract inside a rolled-back transaction. Run
`python -m pytest tests/test_admin_user_reporting.py tests/test_server_monitoring.py`.
Integration checks skip explicitly if that dedicated localhost DB is absent; test
rows and role changes roll back. Run `python examples/admin_user_reporting_demo.py`;
the default `python examples/minimal_demo.py` remains supported.

Final acceptance requires local Grafana/frontend/API/MCP, real model activity and
migrated/seeded PostgreSQL. Reconcile rows to panels, verify ordinary-user denial
through data-source query/proxy APIs and capture final screenshots/manifests under
ignored `runs/e2e/issue806/` for at most seven days. Follow
`docs/E2E_TEST_EVIDENCE_RULE.md`; missing prerequisites leave E2E pending.

The reproducible local checks use `scripts/check_admin_user_reporting_grafana.py`
with a fresh, isolated Grafana 13.0.2 on port 3806 and `issue806_reporting` on port
5432. Mount Grafana data under ignored `runs/storage/grafana806/`. The script rotates
fresh-instance credentials, checks restricted queries, and prepares a temporary
browser session under `runs/storage/`; never attach that session as evidence.
`--refresh-dashboard` updates the local test dashboard from that authenticated session.

For full-path testing, create `issue806_e2e_laws` on local port 5433 with the
start-postgres skill, import the approved real E2E credential with the repository's
SSH importer, then run `scripts/run_issue806_e2e_service.py api` and `mcp` (ports
8806/8706). This explicitly maps approved E2E settings, seeds the existing synthetic
law fixture into this task's PostgreSQL database, and uses cached embeddings offline.
Start the frontend on port 5806 pointing to API 8806. Seed a synthetic paid account
with `scripts/prepare_issue806_e2e_user.py`; `--allow-retest` permits multiple cases.
Log in through the real frontend. `--otp` transfers only that synthetic account's
local PostgreSQL outbox code to the temporary runtime login file, without printing it.
`scripts/issue806_private_browser_step.py` uses Playwright CLI and redacts credentials
from its output and generated login snapshots.

Create a case named `Issue806 final PostgreSQL model verification` in the frontend,
submit a synthetic question and wait for the real answer. Save final-state screenshots
as `03-final-frontend.png` and `04-final-grafana.png` in the same run evidence directory
created by the Grafana check. Run `scripts/verify_issue806_e2e.py --evidence <directory>`
to reconcile ledger tokens, assert real provider/model and local services/seeds,
verify ordinary-user query/proxy denial, and write a sanitized final manifest.

After review, stop only these test services and remove the isolated Grafana container,
its runtime data, the two temporary login/session JSON files, and task-specific
PostgreSQL databases. Drop the test reporting role only after verifying it has no
dependencies outside these databases. Unit/integration test records otherwise roll
back. Keep only sanitized evidence for at most seven days.

### Follow-up #815 acceptance

Reuse the #806 local E2E helpers in an ignored task-runtime copy with paths rooted
at this checkout, task tag `815`, API/Grafana/frontend ports `8815/3815/5915`, and
both task databases (`issue815_reporting`, `issue815_e2e_laws`) on PostgreSQL port
5815. MCP can use unused port 8706. Do not reuse another task's database or services.
Use the current approved `azurefoundryeu:gpt-5-mini` route via the server credential
importer, selecting it explicitly for the synthetic paid account's task policies;
verify both provider and model from the resulting ledger. Preserve the original
helpers as historical #806 reproduction instructions.

Seed an additional synthetic account with 1,000,000 recorded tokens, then hard-delete
that account. In Grafana assert it remains first with the deleted label, no email,
and 1,000,000 total (800,000 input including 200,000 cached, plus 200,000 output).
After the real frontend question, reconcile its ledger to both token tables, verify
13 retained users and latest registration email, and check a selected end before
the seed time returns zero users. Test ordinary-user query/proxy denial and TLS
`verify-full` data-source health. Capture final frontend/dashboard screenshots and
the sanitized manifest under `runs/e2e/issue815/<run-id>/`; never retain login state
or OTPs in evidence. Remove task service processes/containers and runtime credentials
after verification; retain sanitized evidence at most seven days.
Run `python scripts/verify_admin_user_statistics_e2e.py --evidence <run-directory>`
after the base real-model verifier; it adds the selected-date, email, deleted-ranking,
reconciliation and verified-TLS assertions to the sanitized final manifest.

Validation on 2026-09-16: local real GPT-5-mini/frontend/API/MCP/PostgreSQL/Grafana
acceptance passed. The retained synthetic user count was 13; the deleted synthetic
account ranked first with 1,000,000 tokens, while the real-model request reconciled
42 input + 986 output = 1,028 recorded tokens (estimated, explicitly disclosed).
Ordinary-user query and proxy denial and database `verify-full` TLS passed.
The final screenshots/manifest remain only under ignored `runs/e2e/issue815/`.
