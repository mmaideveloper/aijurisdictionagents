# Repo Codex Automations

This directory stores the repository-owned automation templates for Codex Desktop.
The executable automation files still live in the local Codex profile under
`$CODEX_HOME/automations/<automation-id>/automation.toml`.

Use the sync script to install or refresh these templates on a machine:

```powershell
.\scripts\sync_codex_automations.ps1 -DryRun
.\scripts\sync_codex_automations.ps1
```

To sync one automation:

```powershell
.\scripts\sync_codex_automations.ps1 -AutomationId implementation-agent
```

The `__REPO_ROOT__` placeholder is replaced with the absolute path of the current
checkout. Automation memory files are intentionally not tracked or copied.

## Codex Desktop Initial Setup

Codex Desktop uses the local GitHub CLI authentication for the same Windows user.
Refresh project scopes once per machine before relying on Project V2 automations:

```powershell
gh auth refresh -s read:project -s project
gh project item-list 5 --owner mmaideveloper --format json --limit 1
```

If Project V2 cannot be read, the implementation agent must stop and must not
select tasks from issue text alone.

If Codex Desktop cannot store environment variables directly, use the repository
setup helper to read a local `.env` token and verify `gh` access:

```bash
bash .automation/codexdesktopsetup /c/Projects/aijuristiction/aijurisdictionagents/.env
```

The helper accepts `GH_TOKEN`, `GITHUB_TOKEN`, or `GH_PROJECT_TOKEN` and never
prints token values.

## Current Automations

Automation chain contract: `idea-task-agent` -> `prepare-task` -> `implementation-agent` -> review/merge -> `deployment-agent`. Implementation must start only from tasks that contain both readiness markers (`Idea Task Status: Ready for prepare-task.` and `Status: Ready for implementation.`).

- `idea-task-agent`: interactive idea shaping pass for `/idea-task` prompts; asks focused questions, performs repository/compliance review, and outputs a draft ready for `prepare-task`.
- `implementation-agent`: selects ready implementation tasks, moves them through project status, implements, fixes required validation failures, opens a PR, and moves successful work to In review.
- `deployment-agent`: monitors failed deployment/build workflows and creates implementation-ready GitHub tasks for distinct unresolved failures.
- `merge-agent`: closes out safe PRs by checking review status, checks, mergeability, linked task state, merge, issue comments, branch cleanup, and project status.
