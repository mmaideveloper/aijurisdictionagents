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

## Current Automations

- `implementation-agent`: selects ready implementation tasks, moves them through project status, implements, fixes required validation failures, opens a PR, and moves successful work to In review.
- `deployment-agent`: monitors failed deployment/build workflows and creates implementation-ready GitHub tasks for distinct unresolved failures.
- `merge-agent`: closes out safe PRs by checking review status, checks, mergeability, linked task state, merge, issue comments, branch cleanup, and project status.
