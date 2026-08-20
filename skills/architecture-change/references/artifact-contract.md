# Architecture Artifact Contract

Use stable identifiers and repository-relative links.

| Artifact | Identifier | Default path | Lifecycle |
|---|---|---|---|
| Use case | `UC-NNN` | `architecture/use-cases/UC-NNN-<slug>.md` | Draft, Reviewed, Approved, Retired |
| Architecture Design Document | `ADD-NNN` | `architecture/design/ADD-NNN-<slug>.md` | Draft, In Review, Approved, Superseded |
| C4 view | `<system>-<state>-<view>` | `architecture/diagrams/<system>/` | Conceptual, Current, Transition, Target |
| Decision | `ADR-NNN` | `architecture/decisions/ADR-NNN-<slug>.md` | Proposed, Accepted, Rejected, Deprecated, Superseded |
| Conformance review | `ACR-NNN` | `architecture/reviews/ACR-NNN-<slug>.md` | Draft, Complete |

Each artifact must include:

- status, owner when known, date, and scope;
- links to upstream and downstream artifacts;
- evidence and uncertainty labels;
- GDPR/EU AI Act applicability and safeguards;
- unresolved questions and follow-up owners when known.

Use the next unused number in the relevant folder. Never renumber an existing artifact.
