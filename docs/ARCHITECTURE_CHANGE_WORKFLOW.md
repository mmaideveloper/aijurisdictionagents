# Architecture Change Workflow

Repository-local Codex skills provide a repeatable architecture practice that can later be adapted to AGEL governance.

## Flow

```text
Use Case -> ADD draft -> C4 views -> ADRs -> reconcile ADD/C4 -> Implementation -> Conformance review
```

The flow is iterative. C4 work can expose a missing decision; an accepted ADR can require an ADD or target-view update. Implementation starts only after blocking questions and compliance conflicts are resolved.

## Skills

| Skill | Responsibility |
|---|---|
| `$architecture-change` | Coordinate lifecycle, traceability, gates, and readiness |
| `$generate-use-case` | Draft/refine stakeholder behavior and requirements |
| `$generate-add` | Describe the overall architecture design |
| `$generate-c4` | Generate the appropriate source-backed C4 view |
| `$generate-adr` | Record one independently changeable decision |
| `$review-architecture-conformance` | Compare implementation with authoritative artifacts |

One C4 skill supports multiple views because evidence, naming, state, boundaries, and validation rules are shared. Templates are provided for context, container, component, dynamic, and deployment views. Create only the views needed to answer a concrete stakeholder question.

## Default Artifact Layout

```text
architecture/
  use-cases/UC-NNN-<slug>.md
  design/ADD-NNN-<slug>.md
  diagrams/<system>/<system>-<state>-<view>.mmd
  diagrams/<system>/<system>-<state>-<view>-evidence.md
  decisions/ADR-NNN-<slug>.md
  reviews/ACR-NNN-<slug>.md
```

Existing repository layouts may be preserved, but each artifact must use stable identifiers and reciprocal repository-relative links.

## Lifecycle and Authority

- A use case remains `Draft` until stakeholder feedback is incorporated. `Reviewed` or `Approved` requires a cited authoritative source.
- An ADD remains `Draft` or `In Review` until its approval is evidenced.
- An ADR remains `Proposed` until an authorized decision source accepts or rejects it. Accepted decision history is immutable; changes use superseding ADRs.
- Proposed artifacts inform analysis but do not bind implementation.
- A conformance review reports drift; it does not silently rewrite code or architecture decisions.

## Evidence and Compliance

Material claims are labeled `Confirmed`, `Assumption`, `To verify`, or `Unknown`. Architecture artifacts must not contain real personal/health data, credentials, secrets, or sensitive operational details.

Every stage evaluates GDPR and EU AI Act applicability, including data minimization, lawful basis or consent, purpose limitation, retention/deletion, transparency, traceability, and meaningful human oversight. An unresolved compliance conflict blocks implementation readiness.

## Minimal Training Run

```text
Use $architecture-change for “case document sharing”. Start with a draft use case only and list stakeholder questions.
```

After review:

```text
Use $generate-add with UC-001. Create only the C4 views that answer a concrete design question, and list ADR candidates.
```

After implementation:

```text
Use $review-architecture-conformance to compare this branch with UC-001, ADD-001, linked C4 views, and accepted ADRs.
```

The repository skill sync and discovery demonstration remains available through `python examples/project_skills_demo.py`. The default `python examples/minimal_demo.py` prints the architecture workflow contract as part of its output.
