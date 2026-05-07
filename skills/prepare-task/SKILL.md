---
name: prepare-task
description: Prepare an idea or GitHub Project task for implementation in this repository. Use when the user asks to refine an idea, prepare a task, make a GitHub Project item ready, update a task description, create a task from an idea, or ask the necessary technical/product/compliance questions before implementation. Works with existing GitHub issue/project task descriptions or new ideas that need to become implementation-ready work items.
---

# Prepare Task

## Overview

Turn a loose idea or existing GitHub Project task into an implementation-ready task description. Review repository context first, ask only necessary questions, and update the existing task description or create a new issue/project task when no task exists.

## Workflow

1. Identify the source.
   - If the user gives a task or issue URL/number, read the issue body, comments, labels, project fields, and linked PRs when available.
   - If the user gives only an idea, treat it as the source text and ask whether to update an existing task only when a matching task cannot be confidently found.
   - If the user asks to read ideas from a task description, use that description as the authoritative idea source.
2. Review repository context before asking detailed questions.
   - Search docs, examples, tests, source packages, API/mobile/frontend folders, workflows, and existing skills for related patterns.
   - Check `AGENTS.md` instructions and any project-specific skill files that apply.
   - Use `scripts/project_status.ps1` when GitHub Project status context is needed and `gh` has `read:project` plus `project` scopes.
3. Run the compliance readiness check before proposing implementation details.
   - Apply GDPR privacy-by-design and data-minimization.
   - Identify personal data, special categories, legal-risk outputs, retention/deletion needs, consent needs, user transparency, audit logging, and human oversight.
   - Apply EU AI Act expectations for legal-risk outputs: traceability, transparency, human review, risk controls, and clear limitations.
   - If the idea conflicts with GDPR or EU AI Act expectations, stop and propose a compliant alternative instead of marking the task ready.
4. Ask focused questions until the task is ready.
   - Ask no more than three questions at a time.
   - Prefer questions that unblock architecture, user flow, data handling, external services, acceptance criteria, rollout, or test strategy.
   - Avoid asking questions already answered by repository context or the task description.
5. Draft or update the task description.
   - If an issue/task exists, insert the prepared details into that issue description.
   - If no task exists, create a new GitHub issue in the repository and add it to the appropriate GitHub Project when possible.
   - Keep the existing description content unless it is obsolete; add a structured "Prepared Technical Details" section.
6. Mark readiness clearly.
   - Do not move the task to Ready unless the user asks or the repository workflow requires it and all readiness criteria are met.
   - If questions remain, leave a "Not Ready Yet" section with exactly what is missing.

## Repository Review Checklist

Review only the areas relevant to the idea, then summarize what was learned:

- `docs/` for architecture, setup, compliance, deployment, and feature documentation.
- `examples/minimal_demo.py` and related focused demos for runnable example expectations.
- `src/` for system core agent/orchestration/evaluation/logging patterns.
- `api/aijuristiction-api/` for API behavior, migrations, and versioning impact.
- `mobile_app/` for Flutter UX/versioning impact.
- frontend folders for React/UI work; do not execute conda commands for frontend-only tasks.
- `.github/workflows/`, `infra/`, and `docs/GITHUB_ENVIRONMENTS.md` for deployment/input changes.
- `databases/<projectname>/` and `runs/storage/<projectname>/` rules for database-related work.

## Question Areas

Ask questions only where the answer is missing or ambiguous:

- Goal: user value, target persona, success metric, and non-goals.
- Scope: affected platform, API/mobile/frontend/core/docs/infra boundaries, and rollout constraints.
- Data: personal data categories, input/output records, retention, deletion, consent, and audit needs.
- Legal-risk output: whether the feature advises, drafts, judges, scores, classifies, or automates legal decisions.
- Architecture: components, orchestration, agents/tools, persistence, external services, and failure modes.
- UX/API contract: screens, endpoints, request/response shape, permissions, errors, and localization.
- Testing: unit, integration, e2e, visual, migration, privacy/compliance, and deterministic mock coverage.
- Operations: logging, telemetry, secrets, environment variables, GitHub Environment setup, and deployment.
- Documentation: docs to update and minimal runnable example expectations.

## Prepared Description Format

Use the template in `references/task-description-template.md` when writing the issue/task body. Keep sections concise and concrete.

Always include:

- Problem / idea source
- Repository context reviewed
- Proposed technical approach
- GDPR and EU AI Act readiness
- Data/storage impact
- API/UI/agent behavior
- Acceptance criteria
- Test plan
- Documentation and minimal runnable example
- Open questions or "Ready for implementation"

## GitHub Handling

- Prefer `gh issue view`, `gh issue edit`, and GitHub Project commands over manual browser updates when available.
- For backend/system tasks, use project `https://github.com/users/mmaideveloper/projects/5`.
- For frontend tasks, use project `https://github.com/users/mmaideveloper/projects/6`.
- If creating a new issue, use a clear title, the prepared body, and add it to the matching project/status when possible.
- If updating an existing issue, preserve user-provided idea text and append or refresh the prepared technical section.
- Comment when meaningful decisions are made, but avoid noisy comments for every small edit.

## Ready Criteria

A task is ready for implementation only when:

- The implementation scope and non-goals are explicit.
- Compliance risks are identified with mitigations or declared out of scope.
- Data handling, persistence, retention/deletion, and consent are clear when relevant.
- A technical approach names likely files/modules, interfaces, and migration/versioning impacts.
- Acceptance criteria are testable.
- Test and documentation requirements are specific.
- The minimal runnable example requirement is named, defaulting to `python examples/minimal_demo.py`.
- No blocking questions remain.

## Minimal Example

After preparing or updating a task, confirm that the description states how implementation should update or add a minimal runnable example. The default is:

`python examples/minimal_demo.py`
