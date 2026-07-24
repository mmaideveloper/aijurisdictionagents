---
name: implement-jurisdigta-task
description: Implement one Ready Jurisdigta GitHub task from the latest origin/main in a dedicated branch and worktree, with repository review, GDPR and EU AI Act safeguards, unit tests for every new behavior, applicable Playwright E2E coverage, privacy-safe screenshot evidence, documentation, commit, pull request, and task status updates. Use when a user asks to implement, build, fix, or complete a task, issue, bug, or product change in mmaideveloper/aijurisdictionagents.
---

# Implement a Jurisdigta Task

Implement exactly one task from a clean, current `origin/main` baseline and leave reviewable code, tests, evidence, documentation, and GitHub state.

## Preconditions

1. Identify the GitHub issue/task and confirm it is `Ready`.
2. Read the full issue, comments, acceptance criteria, project fields, linked work, the complete live `AGENTS.md`, and relevant repository code and documentation.
3. Ask focused questions before implementation when behavior, acceptance criteria, data handling, or risky assumptions are unclear.
4. Run the GDPR and EU AI Act gate. Apply data minimization, consent where required, retention/deletion controls, transparency, traceable privacy-safe logging, and human oversight for legal-risk outputs. Stop and propose a compliant alternative for unresolved conflicts.
5. Confirm the current checkout does not contain work for another task. Never mix tasks in one branch or worktree.
6. Read and apply [repository-implementation-contract.md](references/repository-implementation-contract.md). Treat it as a current checklist, not a replacement for live repository instructions. When it differs from `AGENTS.md`, the live `AGENTS.md` in the task worktree wins.

## Create the implementation worktree

1. From an existing clean repository checkout, run `.\scripts\sync_env_profile.ps1 -Mode Pull -Profile codex-agent` before the first project command. Inspect only redacted key status.
2. Run `git fetch origin main`.
3. Confirm `origin/main` resolved successfully and record its commit SHA.
4. Create a unique `codex/<task-id>-<slug>` branch and separate worktree from that exact `origin/main` using:

   ```powershell
   .\scripts\new_task_worktree.ps1 `
     -Branch "codex/<task-id>-<slug>" `
     -Base "origin/main"
   ```

5. Do not use raw `git worktree add` when the helper is available.
6. Enter the new worktree and verify the branch, base SHA, and clean `git status`.
7. Read the new worktree's complete `AGENTS.md` again because the latest `origin/main` version is authoritative.
8. Run `.\scripts\sync_env_profile.ps1 -Mode Pull -Profile codex-agent` in the task worktree before its first project command or edit. Inspect only redacted key status.
9. For Python work, use the worktree's `.\conda` environment. For frontend-only work, do not run conda commands.
10. Move the GitHub task to `In progress` before editing.

## Implement

1. Make the smallest coherent change that satisfies the acceptance criteria.
2. Follow every applicable item in the live `AGENTS.md` and the repository implementation contract, including typing, linting, error handling, versioning, database layout, environment variables, provider defaults, infrastructure documentation, Azure authentication, and health monitoring.
3. Keep secrets, private keys, `.env`, runtime databases, raw logs, user content, and test artifacts with personal data out of Git.
4. Update affected documentation and add or update the minimal runnable example, defaulting to `python examples/minimal_demo.py`.
5. If new requirements emerge as an independent change, stop and create a separate task, branch, and worktree.

## Test gate

Follow [test-and-evidence-gate.md](references/test-and-evidence-gate.md).

1. Add or update unit tests for every new or changed behavior. A code feature is not complete without focused unit coverage.
2. Run the narrow tests during development, then all repository-mandated validation for affected components.
3. Evaluate E2E feasibility explicitly:
   - add or extend Playwright tests when the change has a browser-visible flow, browser/API integration, authentication flow, download/upload, generated document, localization, responsive/layout, or other end-to-end behavior that Playwright can meaningfully verify;
   - use the existing frontend or API-integrated Playwright suite selected by the reference;
   - when Playwright is not applicable, record the concrete reason and the strongest alternative integration/contract test.
4. For applicable Playwright coverage, assert behavior rather than relying only on screenshots.
5. Capture privacy-safe screenshots for meaningful visual checkpoints, using synthetic test data and no secrets or personal/legal-case data.
6. Rerun failing tests after fixing the cause. Do not hide failures by weakening assertions or silently changing providers.

## Evidence and GitHub completion

1. Review every screenshot for personal data, credentials, tokens, real emails, case facts, filenames, browser profile details, and unrelated desktop content. Redact or regenerate unsafe evidence.
2. Store reproducible test artifacts under ignored `runs/` paths. Commit only intentionally selected, sanitized review screenshots under the repository's established `docs/screenshots/issue-<id>/` convention when durable evidence is useful.
3. Prepare a validation summary containing:
   - `origin/main` base SHA;
   - unit tests added and commands/results;
   - E2E feasibility decision;
   - Playwright tests and results when applicable;
   - screenshot paths/links when applicable;
   - skipped or blocked checks with exact reasons;
   - GDPR and EU AI Act controls verified.
4. Commit only task-scoped files and push the task branch.
5. Open a pull request targeting `main`. Include the validation summary and render or link sanitized screenshots in the PR body.
6. Add the same completion summary and screenshot links to the GitHub issue/task. Add the comment `Implemented by Codex`.
7. Move the task to `In review` only after the commit exists and the PR is open.
8. Return the task, branch, commit, PR, test results, and evidence links to the user.

## Completion rules

- Do not claim a test passed unless its command completed successfully.
- Do not claim E2E is impossible without evaluating the existing Playwright suites and recording a specific reason.
- Do not use a screenshot as the sole assertion.
- Do not publish screenshots before privacy review.
- Do not move a task to `In review` when required tests fail, the PR is missing, or blocking compliance gaps remain.
