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

- [UC-001: Submit questions and safely execute commands by speech](use-cases/UC-001-speech-input-and-safe-command-execution.md) — Draft

## Current designs

- [ADD-001: Governed speech question and command routing](design/ADD-001-governed-speech-command-routing.md) — Approved, conceptual target
- [ADD-001 implementation task plan](design/ADD-001-implementation-task-plan.md) — Draft task preparation

## Current decisions

- [ADR-001: Route speech-derived commands only through policy-enforced registered capabilities](decisions/ADR-001-route-speech-commands-through-policy-enforced-capabilities.md) — Accepted

## Workflow

Use `$idea-task` for discovery. It routes ordinary changes to `$prepare-task`, user or business behavior to `$generate-use-case`, material business choices to `$generate-bdr`, and architecture-significant changes to `$architecture-change`.

Do not copy generic toolkit skills into this repository. Install the pinned toolkit with `python scripts/sync_aiarchitect_toolkit.py`; JurisDigta-specific rules remain in `AGENTS.md` and [`toolkit-profile.yaml`](toolkit-profile.yaml).
