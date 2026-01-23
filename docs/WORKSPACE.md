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

## Minimal runnable example

After activating the local environment, run:

```bash
conda activate ./.conda
python examples/conda_workspace_smoke.py
```

The script prints the active Python executable and verifies the `.conda` path.
