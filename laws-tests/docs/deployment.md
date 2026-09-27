# Public law reader prerequisite

The dedicated profile now includes `LAWS_TEST_LAWS_DATABASE_URL`. Run the updated server
profile provisioner to prepare its independent reader credential on encrypted USB and in
the server runtime file. The deployment migration requires the dedicated `laws_tests_reader`
role on the approved PostgreSQL server, creates it if missing and grants SELECT-only source
access. Existing collector migrations and the reviewed bank's concrete legal date/source
versions must be ready before publication. See [law-reader.md](law-reader.md).

# Production deployment

The workflow display name is **LawsTest-Self-Managed-Prod-deploy**. It accepts one
`release_sha`: an immutable 40-character commit already on `main`. It uses lowercase
`prod`, protected self-hosted runner labels `self-hosted, Linux, X64, jurisdigta-prod`,
and the approved host's verified SSH key. It never deploys a branch tip after checking
another commit.

The SSH operator needs passwordless `sudo -n` for the reviewed deployment script; the
workflow invokes it as root to read the restricted secret files. Protect this runner and
environment as privileged infrastructure. The smoke package pins Playwright exactly to
the bundled browser image version; upgrade both together and verify browser launch.

`laws-tests-validation` and `laws-tests-real-e2e` are mandatory exact-SHA checks.
Set repository/environment `LAWS_TEST_REQUIRED_CHECKS` to a JSON array naming every
additional applicable check; an empty/missing/invalid setting must not bypass core checks.
The validation workflow performs database constraints/migrations, Python checks, frontend
builds and container builds. Dispatch its real E2E job on a prepared isolated Windows runner
labelled `laws-tests-e2e` using the protected `test` environment. A skipped job is not success.

The deployment gate runs both before environment approval and inside the deploy job, including
reruns. After configuration checks it builds exact-SHA images, creates a restricted database
backup, provisions the dedicated database/app role if absent, applies checksummed migrations,
deploys the API, checks readiness, deploys the frontend and checks public routing. Any failure
returns a failed release. The bundled `smoke.mjs` exercises public reading, a real one-use
authorization exchange and real-model E-1 evaluation using a temporary synthetic identity.
`smoke_identity.py` creates and deletes that identity through the restricted migration job;
its credentials are captured in a 0600 temporary file, never logs or evidence. Production
E-1 data is supplied by the owner-authorized, visibly unverified preview on an empty bank,
or by a later reviewed import. Password/email-OTP browser login
is separately covered by the mandatory local real E2E check.

Checks with identical names from different workflows must all succeed. Workflow IDs are
resolved through the read-only Actions API; only the newest check for each name/workflow is
considered. A manually dispatched successful real-E2E run can supersede its earlier skipped
run on the same commit, while a frontend success cannot hide an API failure. Unknown external
check suites remain independently required.

## First installation (infrastructure operator)

1. Verify ownership/control of **jurisdigta.eu** and DNS/TLS for **tests.jurisdigta.eu**.
   Cloudflare Tunnel must route this hostname to `http://localhost:8410` on jurisdigta-server.
   Port `8060` belongs to `jurisdigta-document-engine-api`; do not reuse it for tests.
2. Verify the encrypted USB mount at `/mnt/jurisdigta-backup`. Run
   `sudo python3 laws-tests/deploy/provision_profiles.py` on the server. It reads approved
   provider configuration in the existing API container, preserves existing files, generates
   independent local/app credentials and writes redacted status only. No laptop-secret push.
3. Production files: `/srv/jurisdigta/secrets/.env-laws-test` (UID 10840, 0600), and
   `.env-laws-test.migration` (root, 0600). USB authority:
   `jurisdigta-env/profiles/laws-tests/{dev,prod}/.env-laws-test`; migration credentials remain
   under the production directory. API images receive only the runtime file, never the migration
   file. Gated migration creates `laws_tests_identity`, granting only account ID/enabled status,
   device-token validation fields and last-use update access. Audit connection hosts/roles
   without printing passwords. The migration credential needs role/database creation privileges.
4. Install Docker/Compose and create `/srv/jurisdigta/laws-tests/{releases,backups}` with
   operator ownership and backups 0700. Create `deployment.env` with the nonsecret
   `LAWS_TEST_IDENTITY_NETWORK` set to the existing API/PostgreSQL Docker network.
5. Map the tests domain through the existing TLS reverse proxy to `127.0.0.1:8410`.
   The tests `/api/` route proxies to its API container; the PostgreSQL port is not public.
6. Deploy the existing account frontend change exposing `/tests-authorize` on `web.jurisdigta.eu`
   with `VITE_LAWS_TEST_PUBLIC_URL=https://tests.jurisdigta.eu`. Preserve the actual account
   authentication/MFA flow. Do not replace the corporate landing page blindly: configure this
   path to the existing account frontend and verify its SPA assets and sign-in return path.
7. Configure required GitHub variables/secrets per `docs/GITHUB_ENVIRONMENTS.md`. Install the
   bundled synthetic production smoke image. Never use development photographs as reviewed
   production content or copy real customer data into the smoke test.
8. Install `retention.sh` as `/srv/jurisdigta/laws-tests/retention.sh` (0750), and the supplied
   retention service/timer in `/etc/systemd/system`. Enable/start `laws-tests-retention.timer`.
   Confirm account deletion and expired-attempt cleanup. Configure backup retention and a
   deletion replay/reconciliation procedure before restoring a public service.
9. After all checks are successful for the final SHA, dispatch the deployment workflow.
   Retain SHA/check links, schema version, image identifiers and synthetic smoke manifest.
   Update the monitoring task with the enabled tests health target at first release.

## Rollback

Keep the previous `current-sha` and its images. If API readiness or later verification fails,
stop rollout, keep the failed release marked failed and restore the previously verified API/web
images using their release directory and `RELEASE_SHA`. Do not restore a backup over new user
attempts or run destructive schema downgrades automatically. Backward-compatible migrations
allow application rollback; incompatible changes require an operator-reviewed recovery plan.
Before restoring, account for writes since the recovery point and replay deletions/retention.
Never reopen deleted histories by rolling back the application or restoring a stale backup.

This change prepares deployment; production rollout still requires actual DNS/TLS, identity
route, runtime DB role, backup/deletion handling, runner setup, labelled preview or content review, and exact-SHA
checks. Local E2E screenshots alone do not establish those production prerequisites.

The initial owner-authorized preview exception and temporary runner setup are documented
in [preview-release.md](preview-release.md). It changes content publication only; every
exact-commit validation gate still applies.

On a network with an approved enterprise TLS inspection CA, local Docker builds can supply
`--secret id=build_ca,src=<approved-public-CA-bundle.pem>`. The optional BuildKit mount supplies
PIP/npm trust during dependency installation only; it is not copied into images. Never disable
certificate verification. Direct-network CI/server builds use their normal public trust store.
