# Laws Tests

Issue #840 adds an independent API and responsive reader at `tests.jurisdigta.eu`, using
existing JurisDigta accounts. The first **development** bank is **Zbrojný preukaz SK 2026**.
The full reviewed production bank belongs to #841. Development records remain private to
development. The owner-authorized initial production release uses a separately labelled
incomplete `preview` set; see [preview-release.md](docs/preview-release.md).
Both environment examples (root and account frontend) use the confirmed production
hostname `tests.jurisdigta.eu`; local acceptance continues to use loopback URLs.

## Run locally (Windows)

Use a separate task worktree with its `conda` runtime. Docker Desktop, Node 24, Edge,
and verified SSH access to `jurisdigta-server` are required for real acceptance.

```powershell
.\scripts\sync_env_profile.ps1 -Mode Pull -Profile codex-agent
.\scripts\sync_env_profile.ps1 -Mode Pull -Profile laws-tests-dev
$env:PYTHONPATH='laws-tests/api;src'
.\conda\python.exe laws-tests/tests/setup_local.py
.\conda\python.exe -m laws_tests.cli migrate
.\conda\python.exe -m laws_tests.cli seed-development
.\conda\python.exe laws-tests/tests/run_local_service.py tests
```

In separate terminals start `run_local_service.py identity` and `run_local_service.py mcp`.
Run `npm ci` in `laws-tests/web` and `frontend/aijurisdictionfronend`. Run the tests web
with `npm run dev` (8410). Run the existing account frontend with
`VITE_API_BASE_URL=http://127.0.0.1:8413`,
`VITE_LAWS_TEST_PUBLIC_URL=http://127.0.0.1:8410`, and
`npm run dev -- --host 127.0.0.1 --port 8412`.

Do not use a running shared development database for this task. The acceptance helper
uses container `laws-tests-840-postgres`, loopback port 5440 and data under
`runs/storage/laws-tests/postgres/data`. Both the `laws-tests` and synthetic identity
databases are local; approved model credentials are imported using the repository helper.
Stop its services before pulling a rotated development profile. The bootstrap reconciles
only its isolated container password, and refuses containers owned by another worktree.

## Verify

`laws-tests/ruff.toml` explicitly enables the CI import, UTC, exception and subprocess
checks for local validation too; the API configuration inherits it. Run the same command
below before pushing. Subprocess failures retain explicit return-code handling so captured
credentials are never emitted in exceptions. Expected provider/transport/validation errors
mark the attempt as failed; unexpected programming errors propagate rather than being hidden.

```powershell
.\conda\python.exe -m pytest laws-tests/tests -q
.\conda\python.exe -m ruff check laws-tests
cd laws-tests/web
npm run build
npm run test:e2e
```

On an isolated prepared Windows runner, `laws-tests/tests/run_acceptance.ps1` orchestrates
the real services and E2E. It must start with free ports 8410–8414. Unit tests use real
PostgreSQL and narrowly stub external boundaries; only the separate browser acceptance
run is evidence for real Azure Foundry evaluation.

Minimal feature example: `python laws-tests/examples/minimal_demo.py` against the local
API. The repository's `python examples/minimal_demo.py` remains the general offline demo.

## Architecture and invariants

Public law links, exact provision navigation, editorial attribution, source configuration,
and the runnable reader example are documented in [law-reader.md](docs/law-reader.md).

- `api/laws_tests`: FastAPI, PostgreSQL, existing Azure Foundry adapter.
- `web`: React/TypeScript reader, practice, exam, history/export/deletion.
- `databases/laws-tests`: versioned SQL and explicitly development-only seed SQL.
- Existing account frontend `/tests-authorize`: authenticates centrally, then sends its
  device proof to the laws-tests authorization endpoint. Credentials never enter redirect URLs.
- A five-minute state plus browser-bound HttpOnly nonce and one-use code establish a
  12-hour HttpOnly tests session. Exact origin checks and CSRF protect mutations. The
  configured identity database adapter validates existing device tokens and enabled users;
  the tests database holds no copied passwords or identity profiles.
- Questions are either direct (one answer, zero children) or grouped (no answer, one or
  more ordered subquestions each with one answer). Deferred database triggers enforce both.
- Attempt snapshots retain the version evaluated. Valid structured model output supplies
  scores; application code applies `score >= 70`. Failures remain unscored, never failed
  knowledge results. Request IDs prevent duplicate calls; separate retries preserve history.
- Expiry rejects new sessions/submissions before model invocation. Public material and
  private prior results remain readable. No expiry is inferred from the edition name.
- Twelve calendar months are measured by PostgreSQL `interval '12 months'` from submission,
  including month-end adjustment. Hourly cleanup plus request-time purge removes expired
  attempts. User deletion cascades sessions/attempts; progress is derived, not permanently
  cached. The hourly task also removes histories for deleted identities.

## Data protection and release limits

Only question/reference/rules and submitted text go to the model. UI asks users to avoid
personal information and identifies AI feedback as practice, not official certification.
No raw model IO is enabled. Public APIs exclude rules, attempts and draft production content.
Publish only after human review, with the legislation effective on publication day and the
exact legal date recorded. Two blurred A-20 passages are explicitly identified in the seed.
Development review status appears in the course badge; the question footer does not repeat
the development-transcription notice.

Transient screenshots and sanitized manifests live in ignored `runs/issue840/evidence`,
retained for 14 days. Do not upload synthetic-account credentials, outbox data, service logs
or browser authentication traces. The test deletes its attempts after capture. Operators
must delete the dedicated synthetic account/outbox/profile after acceptance when no longer
needed. Database backups stay restricted on the host; apply a maximum 12-month backup
retention and replay deletions/retention cleanup before exposing any restored database.

See [deployment](docs/deployment.md) and [acceptance evidence](docs/acceptance.md).
