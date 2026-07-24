# Jurisdigta Codex Plugin

The repository-local plugin under `plugins/jurisdigta/` provides four guided workflows:

- `report-jurisdigta-bug` collects a description, asks whether the error happened locally or on `jurisdigta-server`, requests optional images, routes to only the matching local or server log source, reviews related code and issues, asks focused questions, and creates a sanitized GitHub bug only after confirmation.
- `manage-jurisdigta-adr` creates, reviews, updates, and supersedes source-backed Architecture Decision Records, then hands architecture-derived tasks to the task-preparation skill.
- `prepare-jurisdigta-task` reviews a request and repository context, recommends improvements, asks questions until no blockers remain, creates the confirmed GitHub issue, sets it to Ready, and comments `Reviewed by Codex`.
- `implement-jurisdigta-task` fetches the latest `origin/main`, creates an isolated task branch/worktree, implements one Ready task, requires unit tests, adds applicable Playwright E2E coverage and sanitized screenshots, then commits, opens a PR, updates the task, and moves it to In review.

## Privacy and human oversight

The incident workflow never reads secret files or database/user content, keeps raw logs ephemeral, minimizes the query by environment, service, and time window, and requires redaction plus confirmation before GitHub publication. A local report never triggers server access; a server report requires permission before bounded remote log retrieval. Potential security incidents or personal-data breaches are routed away from public issues.

The architecture workflow makes GDPR and EU AI Act impacts explicit and does not mark a decision Accepted without approval from the human decision owner.

## Minimal examples

Invoke the bug workflow:

```text
Use $report-jurisdigta-bug. Checkout fails in the web app around 14:20 Europe/Bratislava. Ask whether it happened locally or on jurisdigta-server, request screenshots, inspect only the matching logs, and draft a GitHub bug.
```

Invoke the architecture workflow:

```text
Use $manage-jurisdigta-adr to compare Loki and Azure Log Analytics for incident investigation and draft a Proposed ADR.
```

Invoke the implementation workflow:

```text
Use $implement-jurisdigta-task to implement issue 123 from the latest main branch with unit tests, applicable Playwright E2E coverage, and sanitized screenshot evidence in the task and PR.
```

Invoke the task-preparation workflow:

```text
Use $prepare-jurisdigta-task to review this request, recommend improvements, ask questions until it is implementation-ready, then create it in GitHub with Ready status.
```

These examples are runnable as prompts after installing the repository-local plugin. The bug and architecture workflows stop before external writes until the user confirms the final issue or decision. The implementation workflow performs the task-authorized branch, test, PR, and task-status writes while preserving privacy review for screenshots.

## Validation

Validate the plugin manifest and all skills with the Codex plugin and skill validators before publishing or installing the plugin.
