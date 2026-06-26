# Workspace Setup

This repo expects a local conda environment at `.conda/` so VS Code can auto-detect
and auto-activate the interpreter on open.

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
the new checkout. On this Windows Codex machine it prefers cloning the existing
repo runtime from `C:\Users\maton\Projects\aijurisdictionagents\conda`, stores
the cloned environment under `C:\Users\maton\.codex-envs`, and creates a
`conda/` junction in the worktree. That avoids Windows blocking direct
`python.exe` creation under `.codex\worktrees` while keeping
`.\scripts\validate_api.ps1` compatible.

If no reusable repo environment is found, the helper falls back to creating a
fresh environment from `environment.yml`. Micromamba installed through WinGet is
detected automatically and is called with `--ssl-no-revoke` to avoid Windows
certificate revocation lookup failures seen on this box.

After it finishes, run API validation from inside the new worktree:

```powershell
cd C:\Users\maton\.codex\worktrees\issue-123-short-name\aijurisdictionagents
.\scripts\validate_api.ps1
.\conda\python.exe -m pytest api\aijuristiction-api\tests
```

Use `-FreshEnv` to force a new environment from `environment.yml`. Use
`-CloneEnvFrom` to clone a specific conda prefix. The helper refreshes editable
installs afterward so they point at the new worktree.

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

The script prints the active Python executable and verifies the `.conda` path.

## Task #7 tracking location

Task #7 breakdown/plan is maintained directly in GitHub project task/issue #7 (not in a dedicated repository markdown file).
