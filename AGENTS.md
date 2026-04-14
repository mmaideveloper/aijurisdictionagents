Tech stack (Python/Node), target runtime, dependencies

Architecture: agents, orchestration, documents ingestion, evaluation/judging, logging

Coding standards: typing, linting, tests, error handling

Output requirements: always create/update docs, add minimal runnable example
Minimal runnable example (default): `python examples/minimal_demo.py`

Database layout rule:

- Keep only SQL assets under `databases/<projectname>/` such as migrations, init SQL, and seed data.
- Keep all local runtime database files under `runs/storage/<projectname>/`.
- For local PostgreSQL, use `runs/storage/<projectname>/postgres/data`.
- For local SQLite, use `runs/storage/<projectname>/sqlite/`.
- For any new project, create database SQL assets in `databases/<projectname>/` and local runtime database data in `runs/storage/<projectname>/`.

Environment variable rule:

- Whenever you add a new environment variable to the project, add a documented example entry to `.env.example` in the same change.

LLM provider default rule:

- Treat `azurefoundry` as the default LLM provider for local API and chat simulator starts on every computer that uses this repository.
- Do not silently switch local starts from `azurefoundry` to `mock` just because Azure Foundry credentials are missing or incomplete.
- Use `mock` only when the user explicitly asks for it or when a task clearly requires deterministic offline testing.
- When `azurefoundry` is the default and startup cannot continue, stop and report the exact missing `AZURE_OPENAI_*` settings instead of changing provider implicitly.

GitHub workflow / infra environment rule:

- Whenever you add new parameters to a GitHub workflow, or change infrastructure inputs/required settings, update the documented setup steps for `test` and `prod` GitHub Environments in the same change.
- Keep `docs/GITHUB_ENVIRONMENTS.md` aligned with workflow inputs, required GitHub Environment variables, required secrets, and any new manual setup steps.


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

Ask for implementation of task.  Create for each task separate branch.
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

- `api` at `skills/api/SKILL.md`
  - Purpose: start and health-check local `aijuristiction-api` using the same skill name available on this machine.
  - Script: `.\skills\start-api\scripts\start_api.ps1`
- `chatsimulatr` at `skills/chatsimulatr/SKILL.md`
  - Purpose: start and verify the local chat simulator UI.
  - Script: `.\skills\chatsimulatr\scripts\start_chat_simulator.ps1`
- `start-api` at `skills/start-api/SKILL.md`
  - Purpose: start and health-check local `aijuristiction-api`.
  - Script: `.\skills\start-api\scripts\start_api.ps1`
- `start-postgres` at `skills/start-postgres/SKILL.md`
  - Purpose: start or reuse the local PostgreSQL Docker instance and apply schema updates.
  - Script: `.\skills\start-postgres\scripts\start_postgres.ps1`
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
