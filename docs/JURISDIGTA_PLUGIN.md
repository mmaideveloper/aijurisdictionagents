# Jurisdigta Codex Plugin

The repository-local plugin under `plugins/jurisdigta/` provides two guided workflows:

- `report-jurisdigta-bug` collects a description, asks whether the error happened locally or on `jurisdigta-server`, requests optional images, routes to only the matching local or server log source, reviews related code and issues, asks focused questions, and creates a sanitized GitHub bug only after confirmation.
- `manage-jurisdigta-adr` creates, reviews, updates, and supersedes source-backed Architecture Decision Records and can prepare a related GitHub architecture task.

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

Both examples are runnable as prompts after installing the repository-local plugin. They intentionally stop before external writes until the user confirms the final issue or decision.

## Validation

Validate the plugin manifest and both skills with the Codex plugin and skill validators before publishing or installing the plugin.
