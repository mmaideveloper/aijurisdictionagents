Tech stack (Python/Node), target runtime, dependencies

Architecture: agents, orchestration, documents ingestion, evaluation/judging, logging

Coding standards: typing, linting, tests, error handling

Output requirements: always create/update docs, add minimal runnable example
Minimal runnable example (default): `python examples/minimal_demo.py`

Update request rule:

- Whenever the user asks for any update, first review the relevant existing code and documentation before changing it.
- Ask the user about unclear requirements, ambiguous behavior, missing acceptance criteria, or risky assumptions before implementation.
- Recommend a better solution when the requested approach can be made safer, simpler, more maintainable, more compliant, or easier to test.
- If the request is already clear and the current approach is sound, state that briefly and proceed.


Regulatory baseline rule (GDPR + EU AI Act):

- Every new task, design, and code change must be evaluated against GDPR and the EU AI Act before implementation.
- During implementation, apply privacy-by-design/data-minimization, explicit consent handling where required, retention/deletion controls, user transparency, traceable logging, and human-oversight safeguards for legal-risk outputs.
- If a requested change conflicts with GDPR or EU AI Act expectations, stop and surface the compliance gap plus a compliant alternative.


Database layout rule:

- Keep only SQL assets under `databases/<projectname>/` such as migrations, init SQL, and seed data.
- Keep all local runtime database files under `runs/storage/<projectname>/`.
- For local PostgreSQL, use `runs/storage/<projectname>/postgres/data`.
- For local SQLite, use `runs/storage/<projectname>/sqlite/`.
- For any new project, create database SQL assets in `databases/<projectname>/` and local runtime database data in `runs/storage/<projectname>/`.

Environment variable rule:

- Whenever you add a new environment variable to the project, add a documented example entry to `.env.example` in the same change.
- Whenever `.env.example` changes, update local `.env` from it before sharing runtime configuration. Missing keys must be added to `.env` with the value `unknown-variable` so startup and sync tooling can warn clearly without guessing secrets.
- Before the first project command or code edit for every implementation task, run `.\scripts\sync_env_profile.ps1 -Mode Pull -Profile codex-agent`. Codex must invoke the script and may inspect only its redacted key-name/status output, never `.env` or secret values. If the server is unavailable, run `-Mode Audit -Profile codex-agent -Strict`; continue only with a previously verified local profile. This gate does not apply to read-only review or task preparation.
- Use `.\scripts\sync_env_profile.ps1` for profile-aware audit/bootstrap/pull. The encrypted USB on `jurisdigta-server` is authoritative; developer push is prohibited. `.\scripts\sync_jurisdigta_env.ps1` is legacy and must not be used to publish laptop secrets.
- Keep `.env` and private keys out of Git. The server copy is a runtime secret file, not a shared source-controlled artifact.
- Keep temporary Azure infrastructure values in ignored `.env.dev`; pass it explicitly with `-EnvFilePath .env.dev`. Application startup must not assume `.env.dev` is loaded.

LLM provider default rule:

- Treat `azurefoundry` as the default LLM provider for local API and chat simulator starts on every computer that uses this repository.
- Do not silently switch local starts from `azurefoundry` to `mock` just because Azure Foundry credentials are missing or incomplete.
- Use `mock` only when the user explicitly asks for it or when a task clearly requires deterministic offline testing.
- When `azurefoundry` is the default and startup cannot continue, stop and report the exact missing `AZURE_OPENAI_*` settings instead of changing provider implicitly.

Real local E2E acceptance rule:

- For final acceptance of every future user-facing E2E test, run the newly implemented local frontend, API, MCP server, and every relevant worker/service against local PostgreSQL databases with the current migrations applied and deterministic synthetic data seeded in every database used by the scenario.
- Use the configured default real model unless the task explicitly requires a different model. Deterministic mocks may be used for earlier unit, integration, or browser-regression checks, but a mocked model, mocked database response, Playwright route interception, or fabricated UI state is not final E2E acceptance evidence.
- If a synthetic user requests a model that does not exist or is unavailable, the application must visibly inform the user and fall back to the configured default real model. The E2E test must assert both the disclosure and the actual fallback route. Never fall back to `mock`. If the task's acceptance criteria require validating that exact model, report the real-model E2E as failed or pending instead of treating fallback as task acceptance.
- Use synthetic accounts, cases, documents, identities, and task-specific records. Public legal-source data may be real, but production customer or personal data must not be copied into local E2E storage. Give every run a unique identifier, clean up its records and files, and retain evidence only under the repository's ignored `artifacts/` or `runs/` paths according to `docs/E2E_TEST_EVIDENCE_RULE.md`.
- For MCP or legal-retrieval changes, seed deterministic synthetic law/source records into the relevant local PostgreSQL database, assert that direct MCP/API queries return those records and citations, then create a synthetic case in the real local frontend and assert that a user question produces the same grounded source/citation through the complete frontend -> API -> MCP -> database path.
- Final evidence must include a stable user-visible screenshot and a sanitized result manifest recording the real provider/model route, local services used, synthetic seed/run identifiers, and the expected versus observed source identifiers. It must not expose prompts containing personal data, credentials, tokens, passwords, OTP values, or connection strings.
- If any required local service, PostgreSQL database, migration, synthetic seed, or real-model credential is unavailable, do not report the final E2E as passed; report the missing prerequisite and leave real E2E validation pending.
- Bootstrap an approved real Azure Foundry E2E credential into the branch-local PostgreSQL database with `python scripts/bootstrap_e2e_model_credentials.py`. The script must read only `E2E_AZURE_FOUNDRY_*` values from ignored `.env`, require a loopback PostgreSQL connection, encrypt the credential with `AI_MODEL_CREDENTIAL_ENCRYPTION_KEY`, and never print or commit the secret. Importing the currently approved server credential must use `scripts/import_e2e_model_credentials_from_server.ps1`, which transfers it only over SSH and records only redacted metadata.

GitHub workflow / infra environment rule:

- Whenever you add new parameters to a GitHub workflow, or change infrastructure inputs/required settings, update the documented setup steps for `test` and `prod` GitHub Environments in the same change.
- Keep `docs/GITHUB_ENVIRONMENTS.md` aligned with workflow inputs, required GitHub Environment variables, required secrets, and any new manual setup steps.
- Whenever a task requires manual infrastructure setup outside the repository, update `docs/manual_infrastucture_setup.md` in the same change with the exact future installation/configuration steps, required owners/accounts, secrets, environments, validation steps, and rollback notes.

Production deployment build-gate rule:

- Never deploy to the `prod` or `Prod` GitHub Environment while any build, lint, type-check, unit/integration test, E2E gate, image build, or other required check applicable to the exact deployment commit has failed, been cancelled, is still pending, or is missing.
- Treat every applicable required check as fail-closed: fix the underlying failure in a separate task branch/worktree, rerun the affected checks, and confirm all applicable checks succeed for the exact commit SHA before starting or approving production deployment.
- Do not bypass a failed build by manually dispatching a deployment, rerunning only the deploy job, selecting another workflow entry point, or deploying the same unverified files from a local checkout.
- Record the deployed commit SHA and links to the successful build/check runs in the production deployment evidence. If the commit changes after validation, repeat the build gate for the new SHA.

Production health endpoint rule:

- Whenever you add, expose, rename, or make public a production `/health` endpoint, update `.codex/automations/jurisdigta-monitoring-task/automation.toml` in the same change so the hourly `Jurisdigta Monitoring task` checks it and defines its healthy response contract.


Software Development Life Cycle:

Read task for implementation from project https://github.com/users/mmaideveloper/projects/5 and 
tasks with status "Ready". 

Frontend tasks: read tasks from project https://github.com/users/mmaideveloper/projects/6 (Ready status) and do not execute conda commands.

Mobile app versioning rule:

- For any mobile app code or asset change, increase only the revision/build number in `mobile_app/pubspec.yaml`.
- Keep the semantic version part unchanged unless the user explicitly asks to change it.
- Example: `0.1.4+7` -> `0.1.4+8`, not `0.1.5+8`.

API and system core versioning rule:

- Whenever you change API code under `api/aijuristiction-api`, increase the revision number in `api/aijuristiction-api/pyproject.toml`.
- Whenever you change system core code under `src/`, increase the revision number in `src/aijurisdictionagents/__init__.py` and keep the root package version aligned when applicable.
- Unless the user explicitly asks otherwise, bump only the revision portion of the version, not the major or minor portion.

API validation rule:

- After every API code change under `api/aijuristiction-api`, run `ruff check app tests` and `mypy app` from `api/aijuristiction-api` and fix lint/type-check failures before committing.
- Use `.\scripts\validate_api.ps1` from the repository root for the local equivalent of the API CI lint/type-check gate.
- Before preparing data for commit after API changes, also run the API unit tests with `.\conda\python.exe -m pytest api/aijuristiction-api/tests` from the repository root and fix failures before committing.
- Keep the tracked pre-commit hook under `.githooks/pre-commit` enabled with `git config core.hooksPath .githooks` so API lint/type-check failures are caught before commit and before GitHub workflows start.

Ask for implementation of task. Create for each task separate branch.
For every separate task, bug, or product change, create a separate Git branch and a separate Git worktree before editing files. Do not reuse one checkout or shared working directory for multiple independent tasks.
When creating a new task worktree, use `.\scripts\new_task_worktree.ps1` from an existing repo checkout instead of raw `git worktree add` whenever possible. The helper creates the branch/worktree, clones or creates a conda-compatible runtime, and exposes it as local `.\conda` in the new worktree so API validation scripts can run there. On `.codex\worktrees`, the helper stores the actual env under `C:\Users\maton\.codex-envs` and creates a `conda` junction to avoid Windows blocking direct `python.exe` creation under the worktree path.
Do not implement multiple tasks, bugs, experiments, or unrelated product changes in the same branch or worktree.
Before starting work, check the current branch and `git status`; if the branch or worktree already contains changes for another task, stop and create a new branch and worktree from the correct base branch instead of continuing there.
If a change grows into a second independent task, stop, leave the first task isolated, and move the second task into its own branch and worktree.
If you start working move task to in progress.
Before moving a task to In review:
- Commit your changes.
- Create a pull request targeting `main`.
If you finish change status to In review and send me notice.
Add a comment to the issue: "Implemented by Codex".
Use scripts/project_status.ps1 when possible and ensure gh has read:project + project scopes.

Activate the conda environment in `./conda` before running first project command and remember that information, for the next command check if conda has been ran. Run conda only if task if is implementing
python code.

Azure authentication rule:

- Never use the currently signed-in Azure user for repository Azure work.
- Always authenticate Azure CLI with the service principal from `.env`.
- Always prefer `.\infra\scripts\login_service_principal.ps1` before any `az` command that targets repo Azure resources.
- If Azure credentials appear to point to a different tenant/subscription, re-run the service principal login helper instead of continuing with the current Azure user context.

If the user asks to close a task:
- Review the PR and perform a code review.
- If acceptable, approve and merge to `main`.
- Add a comment to the issue with the review/merge outcome.
- Delete the feature branch and comment that deletion on the issue.
- Move the task to Done (closed).

Custom project skills:

- Generic AI architecture skills are maintained in `https://github.com/mmaideveloper/aiarchitecttoolkit` and pinned by `architecture/toolkit.lock.json`. Install them with `python scripts/sync_aiarchitect_toolkit.py --force`. Keep JurisDigta artifacts under `architecture/` and JurisDigta-specific governance in this repository.

- `idea-task` at `skills/idea-task/SKILL.md`
  - Purpose: shape rough ideas into a validated draft, ask focused clarification questions, and hand off to `prepare-task` once ready.
  - Script: chat skill (no launcher script required)
- `api` at `skills/api/SKILL.md`
  - Purpose: start and health-check local `aijuristiction-api` (delegates to `juris-api` defaults: postgres + azurefoundry on port 8080).
  - Script: `.\skills\juris-api\scripts\start_juris_api.ps1`
- `juris-api` at `skills/juris-api/SKILL.md`
  - Purpose: start local `aijuristiction-api` on `127.0.0.1:8080` with local PostgreSQL (Docker Desktop) and `azurefoundry`.
  - Script: `.\skills\juris-api\scripts\start_juris_api.ps1`
- `chatsimulatr` at `skills/chatsimulatr/SKILL.md`
  - Purpose: start and verify the local chat simulator UI on port `8090`; checks/starts `juris-api` on `8080` first.
  - Script: `.\skills\chatsimulatr\scripts\start_chat_simulator.ps1`
- `chat-simulator` at `skills/chat-simulator/SKILL.md`
  - Purpose: alias skill to start chat simulator UI on port `8090`; checks/starts `juris-api` on `8080` first.
  - Script: `.\skills\chat-simulator\scripts\start_chat_simulator.ps1`
- `testdocument` at `skills/testdocument/SKILL.md`
  - Purpose: generate preview PDFs for every enabled document template through the local API preview renderer and write them under `runs\testdocument\document-template-pdfs`.
  - Script: `.\skills\testdocument\scripts\test_document_templates.ps1`
- `prepare-golden-test` at `skills/prepare-golden-test/SKILL.md`
  - Purpose: quarantine and deterministically validate a native synthetic case-export ZIP, register it as `technical_reviewed`, and promote the same PR to `native_reviewed` only after explicit human approval.
  - Script: `.\skills\prepare-golden-test\scripts\prepare_golden_test.ps1`
- `start-api` at `skills/start-api/SKILL.md`
  - Purpose: start and health-check local `aijuristiction-api`.
  - Script: `.\skills\start-api\scripts\start_api.ps1`
- `laws-collector` at `skills/laws-collector/SKILL.md`
  - Purpose: start and monitor laws collector; defaults to local PostgreSQL on Docker Desktop.
  - Default start rule: when asked to start the laws collector, use the production-style local path unless the user explicitly asks for a smoke test or fixture. Start live ZIP import with PostgreSQL, no cycle cap, and enough live probes to continue from the last processed law cursor to the current tail. The run should first verify/complete archive ZIP import, then monthly ZIP import, then sequentially check from the last processed law. If archive/monthly ZIP imports already completed and a live sequential cursor exists, skip newer ZIP snapshots by default, log the completed ZIP state plus `last_imported_law` and `next_law_to_check`, and continue one-by-one. When current, the expected terminal log is `No new laws for SK, last processed law ... at ...`.
  - Script: `.\skills\laws-collector\scripts\start_laws_collector.ps1`
- `start-postgres` at `skills/start-postgres/SKILL.md`
  - Purpose: start or reuse the local PostgreSQL Docker instance and apply schema updates.
  - Script: `.\skills\start-postgres\scripts\start_postgres.ps1`
- `start-email` at `skills/start-email/SKILL.md`
  - Purpose: start and monitor the local email scheduler against the local API email outbox database.
  - Script: `.\skills\start-email\scripts\start_email_scheduler.ps1`
- `start-mobile` at `skills/start-mobile/SKILL.md`
  - Purpose: start and verify the local Flutter mobile app using the same skill name available on this machine.
  - Script: `.\skills\start-mobile-app\scripts\start_mobile_app.ps1`
- `start-mobile-app` at `skills/start-mobile-app/SKILL.md`
  - Purpose: start and verify the local Flutter mobile app.
  - Script: `.\skills\start-mobile-app\scripts\start_mobile_app.ps1`
- `start-frontend-api` at `skills/start-frontend-api/SKILL.md`
  - Purpose: start the local React frontend wired to the local API and verify readiness.
  - Script: `.\skills\start-frontend-api\scripts\start_frontend_api.ps1`
- `frontend-api` at `skills/frontend-api/SKILL.md`
  - Purpose: alias skill to start frontend wired to API using the same launcher.
  - Script: `.\skills\start-frontend-api\scripts\start_frontend_api.ps1`
- `youtube-shorts-upload` at `skills/youtube-shorts-upload/SKILL.md`
  - Purpose: prepare, validate, upload, and publish a local or HTTPS-hosted video as a YouTube Short with privacy, copyright, AI-disclosure, and final-publication confirmation gates.
  - Script: `.\skills\youtube-shorts-upload\scripts\prepare_youtube_short.ps1`

Deployment info:
Created new domain juridigta.eu
with SSL and subdomains.
jurisdigta.eu, www.jurisdigta.eu, api.jurisdigta.eu,  web.jurisdigta.eu, services.jurisdigta.eu, admin.jurisdigta.eu

E2E evidence rule:

- Every user-facing E2E test must produce at least one final-state screenshot.
- Document-generation E2E tests must also retain the generated PDF, render its first page as an image, and validate PDF structure plus extracted expected text. A screenshot alone is not proof that the PDF is correct.
- Voice E2E tests must use synthetic audio only, verify the recognized transcript before submission, and prove that the same normalized text was sent to the system. Never use recordings of real users.
- Store transient evidence under an ignored `artifacts/` or `runs/` path and document its retention. Evidence must not expose passwords, OTP values, tokens, or real personal data.
- Use `docs/E2E_TEST_EVIDENCE_RULE.md` as the acceptance checklist and evidence naming contract.
