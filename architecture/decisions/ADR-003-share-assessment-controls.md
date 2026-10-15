# ADR-003: Share assessment safeguards through a typed organizational IT context

- Status: Proposed (implementation proposal, no inferred formal approval).
- Date: 2026-10-15; owner: implementation maintainer.
- Upstream: [UC-003](../use-cases/UC-003-organizational-it-legal-analysis.md).
- Downstream: [ADD-002](../design/ADD-002-organizational-it-assessment.md), [#909](https://github.com/mmaideveloper/aijurisdictionagents/issues/909).

Confirmed evidence: existing app/software_assessment performs source/excerpt validation,
case authorization, review and retention. The stakeholder selected SK/EU and document
recommendations only. Generic organizational IT intake differs from software qualification.

Proposal: an optional typed ITContext on the existing bounded facts contract selects
distinct deterministic intake, trusted prompt, case type and graph provenance. Give IT
its own endpoint and history filter; share persistence/model policy/review. No provider
or deployment change. Draft/export paths explicitly reject IT-kind results.

Alternatives: (1) a separate assessment service provides independent evolution but
duplicates security, review, migrations and source validation; (2) prompt-only catalog
configuration is cheaper but cannot enforce typed jurisdiction and purpose intake;
(3) typed shared engine preserves safeguards with a small compatibility surface.
All are viable; proposal (3) best fits current scope and existing reviewed controls.

Consequences: reuse reduces duplicated controls and operating cost; schema changes
need software regression tests, and the historical table/module name remains software
specific. Case-private retention and processing policy are unchanged. No raw data enters
public law searches. AI/legal risk classification remains To verify; no certification.
Reviewers should reconsider a service split if future workflows require different
retention, independent release or storage boundaries. Formal acceptance and real E2E
remain pending; neither this ADR nor passing synthetic tests grants release approval.
