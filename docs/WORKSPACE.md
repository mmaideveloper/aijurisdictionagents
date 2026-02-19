# Workspace Setup

This repo expects a local conda environment at `.conda/` so VS Code can auto-detect
and auto-activate the interpreter on open.

## Create the local conda environment

From the repo root:

```bash
conda env create -f environment.yml -p ./.conda
conda activate ./.conda
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

The script prints the active Python executable and verifies the `.conda` path.

## Task #7 tracking location

Task #7 breakdown/plan is maintained directly in GitHub project task/issue #7 (not in a dedicated repository markdown file).
