---
name: prepare-task
description: Convert an already shaped idea into an implementation-ready GitHub Project task. Prefer tasks reviewed by `/idea-task` first. Use when the user asks to finalize a prepared idea, validate readiness, or mark a project task Ready after technical/compliance details are complete. Accepts `/prepare-task [description]` and `/prepare-task -url [issue-url]`, but if the idea was not reviewed by `/idea-task`, run the idea-task interview subset first and mark the task as not ready until that gap is resolved.
---

# Prepare Task

## Overview

Turn a loose idea or existing GitHub Project task into an implementation-ready task description. In chat, run an interview flow: collect the idea, review repository context, ask only necessary questions, draft the task, and ask for explicit confirmation before creating or updating a GitHub issue/project item.

## Consistency Contract with `/idea-task`

- `prepare-task` is phase 2; `idea-task` is phase 1.
- Accepted sources for `prepare-task`:
  1. `/idea-task` output draft (`Status: Ready for prepare-task`).
  2. Existing issue URL that already contains an idea-task prepared section.
  3. Raw idea text only if `prepare-task` first runs the missing idea-task questions inline.
- Do not mark implementation readiness until both lines exist in the prepared section:
  - `Idea Task Status: Ready for prepare-task.`
  - `Status: Ready for implementation.`


## How to Execute This Skill (VS Code, Codex Web, Codex Desktop)

Use any of these invocation styles in chat:

- Direct skill call: `$prepare-task`
- Slash trigger: `/prepare-task [description]`
- Accepted typo trigger: `/prepar-task [description]`
- Existing issue URL: `/prepare-task -url "https://github.com/mmaideveloper/aijurisdictionagents/issues/318"`
- Existing issue URL with accepted typo: `/prepar-task -url "https://github.com/mmaideveloper/aijurisdictionagents/issues/318"`
- Natural language trigger examples:
  - `Here is my idea for a feature. Prepare the task.`
  - `Turn this into a GitHub task and ask me the missing questions first.`
  - `Read this task description and make it implementation-ready.`

Platform notes:

- **VS Code (Codex extension):** open repository chat and start with `$prepare-task` or a trigger phrase. Keep answering follow-up questions until readiness is reached.
- **Codex Web:** open the repository workspace chat and start with `$prepare-task` or a trigger phrase; confirm before issue/project updates.
- **Codex Desktop:** in the project chat, use `$prepare-task` or the same trigger phrases; workflow and output format should match web/VS Code.

Execution rules:

- Run this skill first for idea intake.
- Start implementation only after the task output says it is ready and blocking questions are resolved.
- When the prompt uses `/prepare-task [description]` or `/prepar-task [description]`, treat the text after the trigger as the idea source and prepare it for a GitHub Project task.
- When the prompt uses `/prepare-task -url [issue-url]` or `/prepar-task -url [issue-url]`, read the GitHub issue URL as the authoritative idea source, including the issue body, comments, labels, project fields, and linked PRs when available.
- If the slash-triggered idea is ready after repository and compliance review, create the GitHub issue/project task without asking whether the user wants a task created, because the slash command already requested that outcome.
- If the slash-triggered URL points to an existing issue and the prepared task becomes ready, write the prepared technical details back to that issue without asking whether to update it, because the URL command already requested that outcome.
- If required details are missing, ask up to three focused questions first and create the GitHub task only after the missing details are answered or the user explicitly accepts a task with open questions.

## Chat Intake

When the user gives a feature idea directly in chat:

1. Treat the message as the initial idea source.
2. Acknowledge that the goal is task preparation, not implementation.
3. Review relevant repository context before asking detailed follow-up questions.
4. Ask up to three focused questions at a time until the ready criteria are met.
5. Show a concise draft task summary.
6. For slash-triggered requests, create or update the GitHub task once the task is ready, or once the user confirms that a task with open questions should be created.
7. For non-slash conversational ideas, ask: "Create a GitHub task for this in the appropriate project?"
8. If the user says not yet, keep the drafted task details in the conversation and list the remaining blockers.

When the user gives an existing GitHub issue URL with `-url`:

1. Read the issue title/body/comments/labels/project status before asking questions.
2. Treat the issue's current wording as the basic idea source and preserve it.
3. Review relevant repository context and compliance requirements.
4. Ask up to three focused missing-detail questions when the issue does not contain enough information for implementation readiness.
5. Draft the prepared technical details in chat after the answers are collected.
6. Write the prepared section back to the same issue at the end of the conversation, preserving original user-provided content unless it is obsolete.

## Workflow

1. Identify the source.
   - If the user gives a task or issue URL/number, read the issue body, comments, labels, project fields, and linked PRs when available.
   - If the user gives `-url` followed by a quoted or unquoted GitHub issue URL, parse that URL as the existing task to prepare.
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
   - If no task exists and the request was slash-triggered, create a new GitHub issue in the repository and add it to the appropriate GitHub Project after readiness is reached.
   - If no task exists and the request was conversational rather than slash-triggered, ask for confirmation before creating a new GitHub issue in the repository and adding it to the appropriate GitHub Project.
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


## Cross-Channel Parity Gate (Chat Simulator / API / Mobile / Frontend)

For any feature that presents or renders user-visible outputs (especially document templates, previews, and PDFs), explicitly verify expected behavior per channel before marking readiness.

Required parity questions (ask when not already answered):

- Which channels are in scope: chat simulator, API direct, mobile app, web frontend, or all?
- Must behavior be identical across channels, or are differences intentional?
- For document/PDF flows, where is rendering performed (server/client/hybrid) and which endpoint/contract is authoritative?
- What authentication/authorization is required per channel for fetching generated outputs?
- What is the expected UX per channel for loading/error/empty/offline states?
- Are share/download/open-in-external-app flows required on mobile/web?

If any in-scope channel behavior remains unspecified, keep the task as **Not Ready Yet** and list blockers under Open Questions.

## Question Areas

Ask questions only where the answer is missing or ambiguous:

- Goal: user value, target persona, success metric, and non-goals.
- Scope: affected platform, API/mobile/frontend/core/docs/infra boundaries, and rollout constraints.
- Data: personal data categories, input/output records, retention, deletion, consent, and audit needs.
- Legal-risk output: whether the feature advises, drafts, judges, scores, classifies, or automates legal decisions.
- Architecture: components, orchestration, agents/tools, persistence, external services, and failure modes.
- UX/API contract: screens, endpoints, request/response shape, permissions, errors, localization, and channel parity expectations.
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
- For `-url` issue preparation, use `gh issue view` to read the issue and `gh issue edit` to write the prepared task description back to the same issue when ready.
- Preserve the original issue description and append or refresh a clearly named prepared section instead of replacing the whole idea.
- For backend/system tasks, use project `https://github.com/users/mmaideveloper/projects/5`.
- For frontend tasks, use project `https://github.com/users/mmaideveloper/projects/6`.
- For mobile app tasks, use the backend/system project unless the task is exclusively frontend web work.
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
- Idea phase evidence is present: `Idea Task Status: Ready for prepare-task.`
- Cross-channel parity (chat simulator/API/mobile/frontend) is explicit for all in-scope channels.

## Minimal Example

After preparing or updating a task, confirm that the description states how implementation should update or add a minimal runnable example. The default is:

`python examples/minimal_demo.py`
