Tech stack (Python/Node), target runtime, dependencies

Architecture: agents, orchestration, documents ingestion, evaluation/judging, logging

Coding standards: typing, linting, tests, error handling

Output requirements: always create/update docs, add minimal runnable example
Minimal runnable example (default): `python examples/minimal_demo.py`

Environment variable rule:

- Whenever you add a new environment variable to the project, add a documented example entry to `.env.example` in the same change.

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
- `start-postgress` at `skills/start-postgress/SKILL.md`
  - Purpose: start or reuse the local PostgreSQL Docker instance and apply schema updates.
  - Script: `.\skills\start-postgress\scripts\start_postgress.ps1`
- `start-mobile` at `skills/start-mobile/SKILL.md`
  - Purpose: start and verify the local Flutter mobile app using the same skill name available on this machine.
  - Script: `.\skills\start-mobile-app\scripts\start_mobile_app.ps1`
- `start-mobile-app` at `skills/start-mobile-app/SKILL.md`
  - Purpose: start and verify the local Flutter mobile app.
  - Script: `.\skills\start-mobile-app\scripts\start_mobile_app.ps1`
