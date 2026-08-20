---
name: generate-use-case
description: Create, refine, and review source-backed architecture use-case documents with actors, goals, flows, requirements, data handling, compliance controls, acceptance criteria, and stakeholder feedback. Use when the user supplies a use-case idea or reference such as UC-001, asks for a draft, or wants an existing use case updated after stakeholder discussion.
---

# Generate Use Case

## Workflow

1. Read `AGENTS.md`, existing use cases, supplied stakeholder notes, and relevant repository sources.
2. Resolve the next `UC-NNN` or the referenced existing use case. Never reuse or renumber an identifier.
3. Copy [assets/use-case-template.md](assets/use-case-template.md); replace every placeholder and remove irrelevant optional sections.
4. Separate stakeholder facts from proposals and assumptions. Ask focused questions when ambiguity changes scope, data handling, acceptance criteria, or risk.
5. Describe the main success flow and material alternate/error flows without prescribing architecture prematurely.
6. Apply the GDPR/EU AI Act checklist in [references/use-case-quality.md](references/use-case-quality.md).
7. Keep status `Draft` while feedback is unresolved. Use `Reviewed` only with a cited stakeholder review source and `Approved` only with explicit authority.
8. Save under `architecture/use-cases/UC-NNN-<slug>.md` unless the repository has an established equivalent.

## Rules

- Use observable, testable language.
- Include only the minimum personal or health data categories needed; never include real subject data.
- Identify human decisions and automation boundaries for legal-, clinical-, or other high-impact outcomes.
- Preserve a concise feedback/change log when updating a reviewed draft.
- Link related ADDs, diagrams, ADRs, tasks, and evidence using repository-relative paths or authorized identifiers.

## Output

Return the draft path, status, assumptions, blocking questions, compliance outcome, and recommended next step (`stakeholder review` or `$generate-add`).
