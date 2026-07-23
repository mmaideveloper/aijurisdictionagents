---
name: manage-jurisdigta-adr
description: Create, update, review, accept, reject, or supersede source-backed Architecture Decision Records and related GitHub architecture tasks for Jurisdigta. Use when a user asks for an ADR, architecture decision, technical option comparison, architecture review, or documentation of a significant Jurisdigta design choice in aijurisdictionagents.
---

# Manage a Jurisdigta Architecture Decision

Document consequential architecture choices in `docs/adr/` with traceable evidence, explicit trade-offs, GDPR and EU AI Act analysis, operational consequences, and a human decision owner.

## Select the operation

- **Create:** assign the next `ADR-NNNN-<slug>.md` number and start with `Proposed`.
- **Update:** preserve decision history and refine a proposed record.
- **Review:** assess evidence, alternatives, compliance, risks, and implementation readiness without changing status unless requested.
- **Accept or reject:** require explicit confirmation from the named human decision owner.
- **Supersede:** create a new ADR, mark the old ADR `Superseded by ADR-NNNN`, and link both records.
- **Create an architecture task:** draft a GitHub issue from the ADR or proposal and require confirmation before creating it.

## Workflow

1. Clarify the decision question, drivers, scope, constraints, decision owner, deadline, and whether the output is an ADR, GitHub task, or both.
2. Review `AGENTS.md`, relevant code, tests, configuration, current architecture documentation, existing ADRs, operational runbooks, and authoritative external sources when needed.
3. Determine whether the choice is significant enough for an ADR. Prefer ordinary documentation for reversible implementation detail with no broad consequences.
4. Identify at least two viable options plus the status quo when meaningful. Apply consistent criteria: fitness, maintainability, security, privacy, compliance, cost, reliability, operability, reversibility, migration effort, and testability.
5. Run the compliance gate:
   - map personal-data flows, lawful purpose, minimization, access, retention, deletion, residency, and processor boundaries;
   - identify AI-system role, risk classification assumptions, transparency, traceability, accuracy, monitoring, and human oversight;
   - stop acceptance and propose a compliant alternative when a material GDPR or EU AI Act gap remains.
6. Draft the record with [adr-template.md](references/adr-template.md). Distinguish verified source facts, repository observations, and reasoned inferences.
7. Ask up to three focused questions when evidence, decision ownership, compliance, or acceptance criteria remain unclear.
8. Present the proposed decision, strongest rejected alternative, irreversible consequences, compliance controls, and open risks for human review.
9. Write or update the ADR only within the requested scope. Do not implement the architecture change unless separately authorized.
10. For a GitHub architecture task, draft the complete issue, show it to the user, and require explicit confirmation before creating it in `mmaideveloper/aijurisdictionagents`.

## Evidence rules

- Link repository sources by path and external sources by canonical URL.
- Prefer official documentation, standards, laws, and primary research.
- Date time-sensitive evidence and record important assumptions.
- Do not invent benchmarks, costs, legal classifications, or stakeholder approval.
- Record dissent and uncertainty when they materially affect the decision.

## Status and write boundaries

- `Proposed` is the default for a new record.
- `Accepted` and `Rejected` require explicit human decision-owner approval.
- `Deprecated` and `Superseded` require a reason and replacement link when applicable.
- Creating or editing an ADR or GitHub issue is a write action. Preview material changes before writing when the user has not already approved the exact change.
- Keep legal and compliance interpretations reviewable by qualified humans; an ADR records engineering assumptions and controls, not binding legal advice.
