# Codex Automations

This repository tracks the Codex Desktop automation definitions that are specific
to `aijurisdictionagents`.

The source templates live under `.codex/automations/<automation-id>/automation.toml`.
The local runnable copies live under `$CODEX_HOME/automations/<automation-id>/automation.toml`.
The repository templates use `__REPO_ROOT__` in `cwds`; the sync script replaces it
with the absolute path of the current checkout.

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

- `implementation-agent`: active implementation worker for Project 5 ready tasks. It reads task descriptions, project status, issue comments, linked PR or review context, moves selected tasks to In progress, implements the requested change, fixes required test/lint/type-check failures before review, opens a PR, comments `Implemented by Codex`, and moves successful work to In review.
- `deployment-agent`: paused monitor that checks recent build and deployment workflow failures, deduplicates unresolved failure patterns, and creates ready GitHub tasks in the correct project.
- `merge-agent`: paused closer that reviews open PRs, skips anything with unresolved reviews or failed/missing checks, merges safe PRs into `main`, comments on linked issues, deletes branches, and moves completed tasks to Done.

## Editing Rules

- Edit the repository template first.
- Run the sync script after changes.
- Keep machine-specific state, run logs, and `memory.md` files out of the repository.
- Keep automation prompts aligned with `AGENTS.md`, `docs/AUTOMATION_POLLING.md`, and the repository project workflow scripts.
- If a validation gate is part of the automation contract, failed tests, lint, and type-checks must be fixed before an implementation task is moved to In review unless the blocker is credentials, external services, destructive data migration, or an unavoidable user decision.

## Minimal Runnable Example

```powershell
.\scripts\sync_codex_automations.ps1 -DryRun
```
