# Local Automation Utilities

This directory stores repository-owned helper scripts for local Codex Desktop
and automation setup. Keep machine-specific state, run logs, tokens, and
`memory.md` files out of this directory.

## Codex Desktop GitHub Setup

Use `codexdesktopsetup` when Codex Desktop cannot store environment variables
directly but can run a setup script during worktree creation.

The script reads a GitHub token from the first available source:

1. `GH_TOKEN` environment variable.
2. `GITHUB_TOKEN` environment variable.
3. `GH_TOKEN`, `GITHUB_TOKEN`, or `GH_PROJECT_TOKEN` in a local `.env` file.
4. Existing `gh` keyring credentials when no token is found.

It never prints token values. If a token is loaded from `.env`, it is passed to
`gh auth login --with-token` so later automation commands can use normal
GitHub CLI credentials.

Minimal runnable example from the repository root:

```bash
bash .automation/codexdesktopsetup
```

If Codex runs from a temporary worktree and the real `.env` is in the primary
checkout, pass the file explicitly:

```bash
bash .automation/codexdesktopsetup /c/Projects/aijuristiction/aijurisdictionagents/.env
```

The token must be able to read GitHub Project V2 metadata. Verify manually with:

```bash
gh project item-list 5 --owner mmaideveloper --format json --limit 1
```

If a token was ever pasted into a screenshot, chat, setup script, or any
tracked file, revoke it in GitHub and create a new one before using this setup.
