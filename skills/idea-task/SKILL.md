---
name: idea-task
description: Interactive idea shaping skill that turns a rough idea into a validated concept draft before prepare-task formalizes it into a Ready implementation task. Use when the user asks for early brainstorming, architecture/risk review, task decomposition, technical debt discovery, or asks questions such as '/idea-task [description]'.
---

# Idea Task

## Purpose

Use this skill before `prepare-task` when an idea is still ambiguous.

`idea-task` does discovery and risk shaping.
`prepare-task` does implementation-ready formalization and GitHub project readiness.

## Invocation

- `$idea-task`
- `/idea-task [description]`
- `I have an idea, help me shape it first`

Works in VS Code, Codex Web, and Codex Desktop repository chat.

## Workflow

1. Parse the idea and restate it in one paragraph.
2. Review repository context relevant to the idea.
3. Run GDPR + EU AI Act pre-check before suggesting implementation details.
4. Ask up to three focused questions at a time.
5. Maintain an `Open Questions` list and close items as answered.
6. Produce an `Idea Draft` with:
   - problem and outcome
   - in-scope/out-of-scope
   - likely modules/files
   - risks and technical debt hotspots
   - observability, logging, and rollback expectations
   - compliance notes
7. Decide status:
   - `Ready for prepare-task`
   - `Blocked` (with reasons)
8. If ready, recommend running `$prepare-task` with the generated draft.

## Question Priorities

Ask only what is needed to remove ambiguity:

- user outcome and success metric
- impacted channels (API, chat simulator, mobile, web)
- data classes, retention/deletion, consent/transparency
- external API dependencies and fallback behavior
- acceptance test shape and release constraints

## Output Template

Use `references/idea-draft-template.md`.

## Guardrails

- Do not start code implementation in this skill.
- Stop and surface compliant alternatives if GDPR/EU AI Act conflicts exist.
- Keep answers concise, concrete, and directly actionable by `prepare-task`.
