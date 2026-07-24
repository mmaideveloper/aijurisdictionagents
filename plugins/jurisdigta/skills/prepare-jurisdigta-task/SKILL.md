---
name: prepare-jurisdigta-task
description: Review a new Jurisdigta feature, bug, architecture follow-up, compliance change, technical-debt item, or other work request; inspect repository and GitHub context; recommend improvements; ask focused questions until requirements are implementation-ready; then create a GitHub issue in mmaideveloper/aijurisdictionagents, add it to the correct project with Ready status, and comment Reviewed by Codex after explicit confirmation. Use whenever a user asks to create, prepare, define, refine, or make a new Jurisdigta task Ready.
---

# Prepare a Jurisdigta Task

Turn a request into one implementation-ready GitHub task. Review and improve the request before creating anything; do not implement it.

## Intake

1. Capture the request, desired user outcome, and source. Accept free text, an ADR, an incident draft, or an existing issue URL.
2. Search `mmaideveloper/aijurisdictionagents` for duplicates or overlapping issues, pull requests, ADRs, and planned work.
3. Read `AGENTS.md` plus relevant code, documentation, tests, workflows, examples, database assets, and deployment runbooks before asking detailed questions.
4. Summarize what the repository already supports and distinguish verified facts from assumptions.

## Review and improve

1. Review the request for correctness, maintainability, simplicity, security, privacy, compliance, operability, observability, testability, rollout, and rollback.
2. Recommend a better approach when it is safer, simpler, more maintainable, more compliant, less duplicative, or easier to test. Explain the trade-off and let the user decide when the recommendation changes scope or behavior.
3. Run the GDPR and EU AI Act readiness gate:
   - identify personal and special-category data, purpose, minimization, consent/transparency, access, retention/deletion, residency, processors, and audit needs;
   - identify AI role/risk assumptions, accuracy, traceability, user disclosure, monitoring, limitations, and human oversight for legal-risk outputs;
   - stop Ready status and propose a compliant alternative when a material gap remains.
4. For user-visible outputs, define channel parity across chat simulator, API, mobile, and web. Record intentional differences.
5. Ask no more than three focused questions per round. Continue review/question rounds until every blocking answer is resolved. Do not ask questions already answered by repository evidence.

## Readiness gate

Use [task-template.md](references/task-template.md). Mark a task Ready only when:

- the problem, user outcome, scope, and non-goals are explicit;
- affected components, interfaces, data, failure behavior, migration/versioning, rollout, and rollback are defined;
- GDPR and EU AI Act risks have controls or are explicitly out of scope;
- channel behavior and permissions are clear for every in-scope surface;
- acceptance criteria are independently testable;
- unit, integration, applicable Playwright E2E, privacy/compliance, and screenshot-evidence expectations are specified;
- documentation and a minimal runnable example are named;
- dependencies and owners are identified;
- no blocking questions remain.

Include both exact readiness markers in the issue body:

```text
Idea Task Status: Ready for prepare-task.
Status: Ready for implementation.
```

If any criterion is unresolved, present a `Not Ready Yet` draft with the blockers and continue asking questions. Never create a task in Ready status merely because the user asks to skip unanswered requirements.

## Confirm and create

1. Show the user the final proposed:
   - issue title and complete body;
   - repository and project;
   - labels, dependencies, and owners when known;
   - Ready status;
   - recommended improvements incorporated or declined.
2. Ask for explicit confirmation before creating or updating the GitHub issue/project item. A slash-style invocation that explicitly says to create the task may count as creation authorization only after the user has answered all blocking questions and reviewed the final draft.
3. Create the issue in `mmaideveloper/aijurisdictionagents`.
4. Add it to:
   - GitHub Project 5 for backend, system core, API, mobile, infrastructure, compliance, or cross-platform work;
   - GitHub Project 6 only for frontend-web-only work.
5. Set project status to `Ready`. Prefer `scripts/project_status.ps1` when available and verify `gh` has `read:project` and `project` scopes.
6. Add exactly one issue comment:

   ```text
   Reviewed by Codex
   ```

7. Read the created issue and project item back to verify title, body, project, Ready status, and comment.
8. Return the issue link, project, status, incorporated recommendations, and any non-blocking follow-ups.

## ADR handoff

Keep task creation separate from ADR management:

- use `manage-jurisdigta-adr` to decide and document architecture;
- use this skill to turn an accepted decision or a clearly scoped architecture investigation into a Ready GitHub task;
- link the ADR in the issue and link the issue from the ADR when both exist;
- do not create an implementation task for a still-undecided architecture choice unless the task itself is explicitly to complete that decision.

## Write and safety boundaries

- Repository/GitHub review is read-only until the final draft is confirmed.
- Never include secrets, raw production logs, personal data, legal-case content, private screenshots, or credentials in the task.
- Creating the issue, adding it to a project, changing status, and commenting are external writes; perform them only within the confirmed scope.
- Do not split one cohesive request into multiple tasks without user agreement. Recommend separate tasks when work has independent delivery, ownership, or rollback boundaries.
