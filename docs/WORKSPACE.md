# Workspace Setup

This repo supports ignored local conda environments at `conda/` and `.conda/`.
Codex task worktrees use `conda/` so `.\conda\python.exe` works consistently
with repository validation scripts. VS Code can also use `.conda/` when created
manually.

## Create the local conda environment

From the repo root:

```bash
conda env create -f environment.yml -p ./.conda
conda activate ./.conda
```

## Create a task worktree with a local environment

When starting a new Codex task, create the branch and worktree through the helper
so the new checkout also contains its own ignored `conda/` environment:

```powershell
.\scripts\new_task_worktree.ps1 `
  -Branch codex/issue-123-short-name `
  -WorktreePath C:\Users\maton\.codex\worktrees\issue-123-short-name\aijurisdictionagents
```

The helper runs `git worktree add`, then prepares an ignored `conda/` runtime for
the new checkout and an ignored local `.env` file. By default it stores the
actual Python environment under
`C:\Users\maton\.codex-envs` and creates a `conda/` junction in the worktree.
That avoids Windows blocking direct `python.exe` creation under protected or
synced checkout paths while keeping `.\scripts\validate_api.ps1` compatible.
Each task branch gets its own environment prefix based on the branch slug, for
example `C:\Users\maton\.codex-envs\issue-123-short-name-conda`.

Use `-InWorktreeEnv` only when you explicitly need the full conda prefix created
inside the checkout instead of a junction.

The helper also bootstraps local configuration before returning:

- If the source checkout has an ignored `.env`, the new worktree `.env` is seeded
  from it.
- Otherwise, if `%USERPROFILE%\.jurisdigta\aijurisdictionagents.env` exists, the
  new worktree `.env` is seeded from that operator-managed file.
- Missing active keys from `.env.example` are appended. Concrete local defaults
  are copied as-is; placeholder/secret values remain `unknown-variable` so local
  startup fails loudly instead of guessing secrets.
- The final worktree `.env` is copied back to
  `%USERPROFILE%\.jurisdigta\aijurisdictionagents.env` for the next worktree.
- Commented optional examples are not automatically activated. The helper also
  removes stale `LLM_PROVIDER=mock`, `OTEL_EXPORTER_OTLP_ENDPOINT=...`,
  `INTERNAL_MCP_BASE_URL=...`, and `MODEL_KNOWLEDGE_CUTOFF_DATE=...` values if
  an older shared seed introduced them, because those commented examples alter
  local runtime behavior.

The shared seed is outside Git and should stay local to an approved workstation
or approved encrypted transfer path. Do not commit it. On another computer,
place the same seed file at the same path or pass `-EnvSeedPath` to a local copy.

With conda, the helper prefers cloning the existing repo runtime from
`C:\Users\maton\Projects\aijurisdictionagents\conda`. If no reusable repo
environment is found, it falls back to creating a fresh environment from
`environment.yml`. Micromamba installed through WinGet is detected automatically,
called with `--ssl-no-revoke`, and uses `environment.yml` directly because
micromamba prefix clone can fail on pip-heavy environments during metadata
inspection.

The helper validates the environment by launching `.\conda\python.exe` and
importing core Windows runtime modules: `select`, `ssl`, and `sqlite3`. If a
previous run left a partial prefix, a local non-junction `conda/` directory
without `python.exe`, or a prefix whose interpreter starts but cannot import
those modules, the helper removes that broken ignored path and recreates it
instead of leaving the worktree pointed at a broken runtime.

After it finishes, run API validation from inside the new worktree:

```powershell
cd C:\Users\maton\.codex\worktrees\issue-123-short-name\aijurisdictionagents
.\scripts\validate_api.ps1
.\conda\python.exe -m pytest api\aijuristiction-api\tests
```

Use `-FreshEnv` to force a new environment from `environment.yml`. Use
`-CloneEnvFrom` to clone a specific conda prefix. The helper refreshes editable
installs with the `dev` extras afterward so they point at the new worktree and
include validation tools such as `ruff`, `mypy`, and `pytest`.

Use `-SkipEnvSync` only when intentionally creating a checkout without local
runtime configuration. Use `-SharedEnvSeedPath` when your approved workstation
stores the ignored seed somewhere else, for example an encrypted local folder:

```powershell
.\scripts\new_task_worktree.ps1 `
  -Branch codex/issue-123-short-name `
  -WorktreePath C:\Users\maton\.codex\worktrees\issue-123-short-name\aijurisdictionagents `
  -SharedEnvSeedPath D:\secure-config\aijurisdictionagents.env
```

Minimal runnable bootstrap demo:

```powershell
.\examples\new_task_worktree_bootstrap_demo.ps1
```

The demo creates an ignored fixture under `runs\new-task-worktree-bootstrap-demo`
and validates the `.env` bootstrap path without creating a Git worktree or conda
environment.

To repair an existing worktree that was created without `conda/`, where
`.\conda\python.exe` is missing, or where Python starts but fails on standard
library imports such as `select`, run the helper in environment-only mode from
any checkout of the repo:

```powershell
.\scripts\new_task_worktree.ps1 `
  -Branch codex/issue-123-short-name `
  -WorktreePath C:\Users\maton\.codex\worktrees\issue-123-short-name\aijurisdictionagents `
  -SetupEnvOnly
```

To repair only the ignored local `.env` without creating or touching the Python
environment:

```powershell
.\scripts\new_task_worktree.ps1 `
  -Branch codex/issue-123-short-name `
  -WorktreePath C:\Users\maton\.codex\worktrees\issue-123-short-name\aijurisdictionagents `
  -SetupEnvOnly `
  -SkipEnvCreate
```

Use `-RecreateEnv` with `-SetupEnvOnly` when the environment folder exists but
must be discarded and rebuilt:

```powershell
.\scripts\new_task_worktree.ps1 `
  -Branch codex/issue-123-short-name `
  -WorktreePath C:\Users\maton\.codex\worktrees\issue-123-short-name\aijurisdictionagents `
  -SetupEnvOnly `
  -RecreateEnv
```

## Open the workspace

Open the workspace file (recommended):

```bash
code aijurisdictionagents.code-workspace
```

If you open the folder directly, ensure the interpreter is set to
`${workspaceFolder}\\.conda\\python.exe`.

For Playwright test discovery in VS Code Testing view, use the dedicated E2E workspace:

```bash
code playwright-e2e.code-workspace
```

This opens `api/aijuristiction-api/e2e-playwright` as the workspace root so the
Playwright extension resolves local `@playwright/test` correctly.

## Open Redirects In Chrome

Workspace settings are configured to open external links/redirects in Chrome:

- `workbench.externalBrowser = "chrome"`
- `liveServer.settings.CustomBrowser = "chrome"`

These settings are present in both `.vscode/settings.json` and
`aijurisdictionagents.code-workspace`.

## Minimal runnable example

After activating the local environment, run:

```bash
conda activate ./.conda
python examples/conda_workspace_smoke.py
```

For Codex task worktrees, the equivalent direct command is:

```powershell
.\conda\python.exe examples\conda_workspace_smoke.py
```

The script prints the active Python executable and verifies that it is running
from either `conda/` or `.conda/` under the repository root.

## Task #7 tracking location

Task #7 breakdown/plan is maintained directly in GitHub project task/issue #7 (not in a dedicated repository markdown file).
