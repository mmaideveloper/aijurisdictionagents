# Codex Automations

This repository tracks the Codex Desktop automation definitions that are specific
to `aijurisdictionagents`.

The source templates live under `.codex/automations/<automation-id>/automation.toml`.
The local runnable copies live under `$CODEX_HOME/automations/<automation-id>/automation.toml`.
The repository templates use `__REPO_ROOT__` in `cwds`; the sync script replaces it
with the absolute path of the current checkout.

## Codex Desktop Initial Setup

Codex Desktop uses the GitHub CLI authentication stored for the same Windows user
account. Before enabling repository automations on a new machine, refresh the
GitHub CLI scopes from a normal PowerShell terminal:

```powershell
cd C:\Projects\aijuristiction\aijurisdictionagents
gh auth refresh -s read:project -s project
```

Verify that the active account can read Project V2 metadata:

```powershell
gh auth status
gh project item-list 5 --owner mmaideveloper --format json --limit 1
```

The implementation agent treats Project V2 access as a hard prerequisite. If the
Project V2 read fails, it must stop instead of selecting work from issue text or
comments.

If Codex Desktop cannot store environment variables directly, use the local
setup helper in the environment setup script. It reads `GH_TOKEN`,
`GITHUB_TOKEN`, or `GH_PROJECT_TOKEN` from `.env`, stores credentials through the
GitHub CLI, and verifies Project V2 access without printing the token:

```bash
bash .automation/codexdesktopsetup /c/Projects/aijuristiction/aijurisdictionagents/.env
```

For temporary worktrees that already contain `.env`, the argument can be omitted:

```bash
bash .automation/codexdesktopsetup
```

## Install or Refresh

Preview the automations that would be installed:

```powershell
.\scripts\sync_codex_automations.ps1 -DryRun
```

Install or refresh all repo automations:

```powershell
.\scripts\sync_codex_automations.ps1
```

Install only one automation:

```powershell
.\scripts\sync_codex_automations.ps1 -AutomationId implementation-agent
```

If `CODEX_HOME` is not set, the script falls back to `$HOME\.codex`.
To install into another profile or test location:

```powershell
.\scripts\sync_codex_automations.ps1 -CodexHome C:\Temp\codex-home
```

## Existing Automation Tasks

- `implementation-agent`: active implementation worker for Project 5 ready tasks. It must first prove that `gh` can read Project V2 metadata, then select exactly one issue whose Project V2 Status is `Ready` and whose readiness section contains `Status: Ready for implementation.`. If Project V2 cannot be read, including missing `read:project` or `project` scopes, it stops instead of selecting work from issue text alone. It rechecks status before claiming, moves the task to In progress, implements the requested change, fixes required test/lint/type-check failures before review, opens a PR, comments `Implemented by Codex`, and moves successful work to In review.
- `deployment-agent`: paused monitor that checks recent build and deployment workflow failures, deduplicates unresolved failure patterns, and creates ready GitHub tasks in the correct project.
- `merge-agent`: paused closer that reviews open PRs, skips anything with unresolved reviews or failed/missing checks, merges safe PRs into `main`, comments on linked issues, deletes branches, and moves completed tasks to Done.

## Editing Rules

- Edit the repository template first.
- Run the sync script after changes.
- Keep machine-specific state, run logs, and `memory.md` files out of the repository.
- Keep automation prompts aligned with `AGENTS.md`, `docs/AUTOMATION_POLLING.md`, and the repository project workflow scripts.
- Keep the implementation agent's Project V2 status gate as a hard stop: it must not implement a task unless the current Project V2 item status is exactly `Ready`.
- If a validation gate is part of the automation contract, failed tests, lint, and type-checks must be fixed before an implementation task is moved to In review unless the blocker is credentials, external services, destructive data migration, or an unavoidable user decision.

## Minimal Runnable Example

```powershell
.\scripts\sync_codex_automations.ps1 -DryRun
```
