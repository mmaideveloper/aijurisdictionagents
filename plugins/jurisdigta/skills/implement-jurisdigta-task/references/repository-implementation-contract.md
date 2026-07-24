# Repository Implementation Contract

This checklist reflects the repository rules at plugin version 0.1.4. Always read the complete live `AGENTS.md` in the task worktree. The live file is authoritative when rules change.

## Task source and lifecycle

- Implement backend/system Ready tasks from GitHub Project 5.
- Implement frontend Ready tasks from GitHub Project 6; do not run conda commands for frontend-only work.
- Confirm requirements and acceptance criteria before implementation.
- Move the task to `In progress` before editing.
- Use `scripts/project_status.ps1` when possible and ensure `gh` has `read:project` and `project` scopes.
- Before `In review`, commit the changes and create a PR targeting `main`.
- On completion, comment exactly `Implemented by Codex`, move the task to `In review`, and notify the user.

## Isolation and baseline

- Use one branch and one worktree per task, bug, experiment, or product change.
- Start from freshly fetched `origin/main`.
- Check branch and `git status` before editing.
- Use `.\scripts\new_task_worktree.ps1`; do not reuse a checkout containing another task.
- If work expands into an independent task, leave the first task isolated and create another branch/worktree.

## Environment and runtime

- Before the first project command or edit, run:

  ```powershell
  .\scripts\sync_env_profile.ps1 -Mode Pull -Profile codex-agent
  ```

- Inspect only redacted key-name/status output; never inspect `.env` values.
- If the server is unavailable, run `-Mode Audit -Profile codex-agent -Strict` and continue only with a previously verified local profile.
- Never publish laptop secrets with the legacy sync script.
- Add every new environment variable to `.env.example` in the same change. Update local `.env` through the repository process, using `unknown-variable` for missing keys.
- Keep `.env`, `.env.dev`, private keys, and runtime secrets out of Git.
- Use `azurefoundry` as the default local LLM provider. Do not silently fall back to `mock`; report exact missing `AZURE_OPENAI_*` settings.
- For Python implementation, use/activate the task worktree's `.\conda` environment before the first project command. Do not use conda for frontend-only work.

## Code, versions, and validation

- Maintain typing, linting, tests, error handling, privacy-safe logs, and the project architecture for agents, orchestration, ingestion, evaluation/judging, and logging.
- For mobile code or asset changes, increment only the build/revision after `+` in `mobile_app/pubspec.yaml`, unless semantic versioning is explicitly requested.
- For API code under `api/aijuristiction-api`, increment only the revision in its `pyproject.toml`.
- For core code under `src/`, increment only the revision in `src/aijurisdictionagents/__init__.py` and align the root package when applicable.
- After API changes:
  - run `ruff check app tests` from `api/aijuristiction-api`;
  - run `mypy app` there;
  - run `.\scripts\validate_api.ps1` from the root;
  - run `.\conda\python.exe -m pytest api/aijuristiction-api/tests`;
  - keep `git config core.hooksPath .githooks`.
- Run component-specific unit tests and all applicable repository validation.
- Add or update documentation and a minimal runnable example, defaulting to `python examples/minimal_demo.py`.

## Database and storage

- Keep only SQL assets in `databases/<projectname>/`.
- Put local runtime database files in `runs/storage/<projectname>/`.
- Use `runs/storage/<projectname>/postgres/data` for local PostgreSQL.
- Use `runs/storage/<projectname>/sqlite/` for local SQLite.

## Infrastructure and operations

- When workflow parameters or infrastructure inputs change, update `docs/GITHUB_ENVIRONMENTS.md` for both test and prod.
- When manual infrastructure setup is required, update `docs/manual_infrastucture_setup.md` with owners/accounts, secrets, environments, validation, and rollback.
- When a production `/health` endpoint is added, exposed, renamed, or made public, update `.codex/automations/jurisdigta-monitoring-task/automation.toml`.
- Before any `az` command against repository resources, authenticate with `.\infra\scripts\login_service_principal.ps1`. Never rely on the currently signed-in Azure user.

## GDPR and EU AI Act

- Apply privacy by design and data minimization.
- Define consent where required, retention/deletion controls, transparency, traceable logging, and human oversight.
- Keep secrets, personal data, legal-case content, prompts, documents, and credentials out of logs, screenshots, issues, and PRs.
- Stop when a request conflicts with GDPR or EU AI Act expectations and propose a compliant alternative.
