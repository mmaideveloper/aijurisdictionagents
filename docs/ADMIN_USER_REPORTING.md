# Admin Grafana user reporting (#806)

The private **JurisDigta Admin Users and Performance** dashboard extends the existing
Application Performance dashboard. Preview with
`python Deployment/monitoring/user_reporting.py --preview`.
PostgreSQL migration `806_admin_user_reporting.sql` installs its reporting contract.
Shared Grafana provisioning never contains the reporting data source or user IDs.

## Definitions and limits

- Total counts current accounts, including disabled accounts, minus explicit service,
  synthetic, deleted or restricted exclusions. It ignores the date selector. Accounts
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
- Latest 10 means registrations within the range, newest first, ties ordered by ID.
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
  and total_rows. Reconciliation separates eligible/excluded/unattributed totals
  without exposing excluded/orphaned identifiers.

Default range: 30 days. Non-finite, empty, reversed or over-366-day ranges and invalid
pagination fail. Refresh: 1 minute. Read-login timeout: 10s; connection limit: 3.
Malformed source timestamps/metadata cause errors, never zeros. Grafana distinguishes
failed queries, empty results and null/unavailable values.

## Privacy and operations

Purpose: internal account adoption and recorded resource usage. User IDs remain
personal data. Before rollout the privacy owner records the processing basis and
confirms privacy-notice coverage; a new consent checkbox is not assumed appropriate.
No names, email, prompts, case facts or credentials enter reports. There is no AI
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
Include this schema in backup expiry/restore deletion procedures. No cached query
results or unapproved exports; browser state clears on logout/close.

Access logs must record authenticated actor, organization, action/path, time, result
and correlation ID without request/response bodies, SQL text, user-ID rows or secrets.
Verify gateway/session audit coverage before production rollout.

## Verification

`./skills/start-postgres/scripts/start_postgres.ps1 -DatabaseName issue806_reporting_tests`
creates the synthetic local database and applies migrations. Run
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
