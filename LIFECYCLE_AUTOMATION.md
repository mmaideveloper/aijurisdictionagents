# Lifecycle Automation

This repository now uses a single lifecycle workflow: an implementation agent powered by Codex CLI.

## Workflow

- Workflow file: `.github/workflows/lifecycle_implementation_agent.yml`
- Workflow name: `lifecycle-implementation-agent`
- Triggers:
  - `workflow_dispatch` (manual run)
  - `schedule` every 15 minutes (`*/15 * * * *`)

Behavior:

1. Select the oldest issue in `Ready` status from the configured Project V2.
2. Move the issue to `In progress`.
3. Run Codex CLI to implement the issue in-repo.
4. Create a feature branch and push changes.
5. Open a pull request to `main` (or configured base branch).
6. Move the issue to `In review`.
7. Add issue comment: `Implemented by Codex` with PR URL.

## Required Secrets

- `GH_PROJECT_TOKEN` with `read:project` and `project` scopes.
- `OPENAI_KEY` for Codex CLI authentication.

## Run the Workflow

Minimal runnable workflow dispatch example:

```bash
gh workflow run lifecycle_implementation_agent.yml \
  -f project_owner=mmaideveloper \
  -f project_number=5 \
  -f repo=mmaideveloper/aijurisdictionagents \
  -f ready_status=Ready \
  -f base_branch=main \
  -f codex_model=gpt-5
```

Watch the latest run from your local machine:

```bash
gh run list --workflow lifecycle_implementation_agent.yml --limit 1
gh run watch
```

## Related Scripts

- `scripts/project_status.ps1`: updates project status and posts optional issue comments.
- `scripts/lifecycle_agent_run.py`: local lifecycle stage runner retained for local experiments.

## Minimal Runnable Example

```bash
python examples/minimal_demo.py
```

## MCP Server Setup (Microsoft Learn)

```bash
codex mcp add "microsoft-learn" --url "https://learn.microsoft.com/api/mcp"
```
