---
name: architecture-change
description: Coordinate a traceable architecture change from stakeholder use case through Architecture Design Document (ADD), C4 views, Architecture Decision Records (ADRs), implementation readiness, and post-implementation conformance review. Use when starting or governing a significant architecture change, checking which artifacts are required, or continuing a change from an existing UC, ADD, C4, or ADR reference.
---

# Architecture Change

Coordinate the workflow; delegate artifact authoring to the focused repository skills.

## Workflow

1. Read `AGENTS.md`, relevant repository sources, and supplied stakeholder evidence.
2. Assign or resolve a change slug and maintain the traceability contract in [references/artifact-contract.md](references/artifact-contract.md).
3. Run `$generate-use-case`. Keep the use case `Draft` until stakeholder feedback is incorporated; require `Reviewed` before design baselining.
4. Run `$generate-add` from reviewed use cases and source evidence. Record uncertainties instead of inventing facts.
5. Run `$generate-c4` for only the views needed to answer stakeholder questions. Do not require every C4 level.
6. Run `$generate-adr` once per independently changeable decision discovered during ADD/C4 work.
7. After ADR acceptance, reconcile the ADD and affected target-state C4 views. Proposed ADRs may inform drafts but are not binding.
8. Declare implementation readiness only when blocking questions are closed, compliance gates pass, accepted decisions are linked, and acceptance criteria are testable.
9. After implementation, run `$review-architecture-conformance` and resolve or explicitly accept deviations.

## Required Gates

- Evidence: label every material claim `Confirmed`, `Assumption`, `To verify`, or `Unknown`.
- Privacy and regulation: address GDPR data minimization, lawful basis/consent where applicable, retention/deletion, transparency, traceability, and human oversight. Stop on an unresolved compliance conflict.
- Safety and security: do not place personal/health data, credentials, secrets, or sensitive operational details in artifacts.
- Governance: never claim stakeholder, architecture-board, security, privacy, or clinical approval without an authoritative source.
- Implementation: architecture work does not authorize code changes. Follow the repository task, branch, worktree, validation, documentation, and versioning rules separately.

## Default Output Layout

```text
architecture/
  use-cases/
  design/
  diagrams/<system-slug>/
  decisions/
  reviews/
```

Preserve an established repository layout when one already exists and note the mapping.

## Completion Summary

Report artifact paths, lifecycle state, evidence gaps, accepted versus proposed decisions, compliance outcome, implementation readiness, and the next responsible action.
