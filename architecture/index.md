# JurisDigta architecture index

This directory owns JurisDigta-specific architecture evidence. The reusable authoring workflow comes from the [AI Architect Toolkit](https://github.com/mmaideveloper/aiarchitecttoolkit) and is pinned in [`toolkit.lock.json`](toolkit.lock.json).

## Artifact locations

| Artifact | Location | State |
|---|---|---|
| Business Decision Records (`BDR-NNN`) | `business-decisions/` | New canonical location |
| Use cases (`UC-NNN`) | `use-cases/` | New canonical location |
| Architecture Design Documents (`ADD-NNN`) | `design/` | New canonical location |
| C4 sources and evidence | `diagrams/<system>/` | New canonical location |
| Architecture Decision Records (`ADR-NNN`) | `decisions/` | New canonical location |
| Conformance reviews (`ACR-NNN`) | `reviews/` | New canonical location |
| Existing architecture documentation | [`../docs/`](../docs/) | Retained; migrate only when touched |
| Legacy ADR | [`../docs/adr/ADR-0001-api-framework-and-streaming.md`](../docs/adr/ADR-0001-api-framework-and-streaming.md) | Retained to avoid breaking links |

## Current architecture views

- [Current architecture review](diagrams/jurisdigta/jurisdigta-current-architecture-review.md)
- [System context](diagrams/jurisdigta/jurisdigta-current-context.mmd)
- [Container view](diagrams/jurisdigta/jurisdigta-current-container.mmd)
- [Diagram evidence](diagrams/jurisdigta/jurisdigta-current-evidence.md)
- [Target governed speech-command container](diagrams/jurisdigta/jurisdigta-target-speech-command-container.mmd)
- [Target governed speech-command dynamic flow](diagrams/jurisdigta/jurisdigta-target-speech-command-dynamic.mmd)
- [Target governed speech-command evidence](diagrams/jurisdigta/jurisdigta-target-speech-command-evidence.md)

## Current use cases

- [UC-004: Private study banks](use-cases/UC-004-private-study-banks.md) — Reviewed owner requirements, #924
- [ADD-003: Private study banks and reviewed processing](design/ADD-003-private-study-banks.md) — In Review
- [ADR-004: Explicit bank grants](decisions/ADR-004-explicit-bank-grants.md) — Accepted product access decision; no release approval implied

- [UC-003: Organizational IT legal analysis](use-cases/UC-003-organizational-it-legal-analysis.md) — scope reviewed, implementation validation pending
- [ADD-002: Organizational IT assessment](design/ADD-002-organizational-it-assessment.md) — In Review
- [ADR-003: Share assessment controls](decisions/ADR-003-share-assessment-controls.md) — Proposed
- [ACR-001: Organizational IT conformance/security review](reviews/ACR-001-organizational-it-assessment.md) — Complete for implementation review

- [UC-002: Review an uploaded Slovak legal document](use-cases/UC-002-review-uploaded-legal-document.md)

- [UC-001: Submit questions and safely execute commands by speech](use-cases/UC-001-speech-input-and-safe-command-execution.md) — Draft

## Current designs

- [ADD-001: Governed speech question and command routing](design/ADD-001-governed-speech-command-routing.md) — Approved, conceptual target
- [ADD-001 implementation task plan](design/ADD-001-implementation-task-plan.md) — Prepared; six dependency-gated GitHub tasks

## Current decisions

- [ADR-002: Case-private extraction and explicit document revisions](decisions/ADR-002-case-document-review-revisions.md) — Accepted for #800/#623

- [ADR-001: Route speech-derived commands only through policy-enforced registered capabilities](decisions/ADR-001-route-speech-commands-through-policy-enforced-capabilities.md) — Accepted

## Workflow

Use `$idea-task` for discovery. It routes ordinary changes to `$prepare-task`, user or business behavior to `$generate-use-case`, material business choices to `$generate-bdr`, and architecture-significant changes to `$architecture-change`.

Do not copy generic toolkit skills into this repository. Install the pinned toolkit with `python scripts/sync_aiarchitect_toolkit.py`; JurisDigta-specific rules remain in `AGENTS.md` and [`toolkit-profile.yaml`](toolkit-profile.yaml).
