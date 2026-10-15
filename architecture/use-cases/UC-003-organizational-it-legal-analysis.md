# UC-003: Establish the legal requirements for an organizational IT initiative

## Record

- Status: Reviewed (scope); implementation and legal validity are not approved.
- Date: 2026-10-15
- Owner/stakeholders: product owner, organizational IT lead, legal/DPO reviewer.
- Project: jurisdigta; instructions: root AGENTS.md and architecture/toolkit-profile.yaml.
- Upstream: [#909](https://github.com/mmaideveloper/aijurisdictionagents/issues/909).
- Downstream: [ADD-002](../design/ADD-002-organizational-it-assessment.md), [ADR-003](../decisions/ADR-003-share-assessment-controls.md).

## Goal, scope and actors

Confirmed by the stakeholder: SK + EU, web/API/chat simulator; recommend actions and
documents for organizational IT, analytics and AI. Success means every displayed
action has an owner, verification expectation and explicit evidential/legal limits.
Mobile, Czech national law, automatic certification and drafting/export are excluded.
The signed-in case owner supplies facts; the system asks relevant questions and
retrieves public provisions; a human legal/DPO reviewer decides whether to rely on
the assessment. The system cannot supply a lawful basis or organizational approval.

## Preconditions and main flow

Authenticated case access and an enabled case type are required. The user selects
Právna analýza pre IT or starts a matching conversation.

1. Describe the initiative without patient-level records.
2. Confirm countries, sector and separate legal entities.
3. Separate intended purposes, data categories and entity roles; identify missing facts.
4. Describe grounds, suppliers/flows, hosting/transfers, security, retention and policies.
5. Supply AI-specific purposes if relevant and transparency/rights arrangements.
6. Acknowledge external processing separately from any patient-data lawful basis.
7. Read a source-grounded preliminary assessment, prioritized actions and document checklist.
8. Supply evidence, request human review and retain case-private reassessment history.

## Alternate and failure flows

| Condition | Behavior and recovery |
|---|---|
| Country CZ or another unsupported code | Stop complete assessment; disclose national-law limit; correct a mistaken code or obtain national legal review |
| Unspecified future purposes | Ask for separate purposes; recommend scoping rather than approving bulk pooling |
| Missing facts or unreadable evidence | Ask or disclose the gap; do not infer a fact or manufacture an excerpt |
| Missing/stale legal sources | Incomplete-source disclosure, no compliance conclusion; human verification/retry |
| Consent withheld/revoked | No external assessment until a new explicit acknowledgment |
| Unavailable selected model | Disclose actual configured real-model fallback or fail; no mock acceptance |

## Information and governance

Case facts/policies may contain confidential or personal data (To classify per case).
Patient-level data is unnecessary. Facts and results are case-private in the existing
assessment store; deletion follows the case lifecycle. Public-source searches use
fixed topics, never case text. No new raw-text logs or secrets are introduced.
GDPR grounds, special-category conditions, retention and rights are questions to
verify, not presumed approvals. AI role/classification is To verify by intended use.
External-processing acknowledgment is not patient consent. Every result requires
human review; declarations do not become verified controls automatically.

## Requirements and acceptance

- FR-01: Distinct selectable/detectable IT case; software-only assessment remains usable.
- FR-02: Missing facts and unsupported jurisdictions prevent external assessment.
- FR-03: Output distinguishes law, contracts/internal policies and recommendations.
- FR-04: Reuse citation, access, evidence and review controls; recommend documents only.
- QA-01: Cross-case read/write is rejected using the existing authenticated API contract.
- QA-02: Direct API and web/chat use the same result and evidence semantics.
- QA-03: Source unavailability yields visible incompleteness rather than invented findings.

Acceptance: synthetic Czech ZdravieHospital remains Czech and triggers the scope
boundary; a separately labelled Slovak 20-entity variant exercises the full flow.
Real Azure Foundry + local PostgreSQL/MCP/frontend evidence is required under
[the evidence rule](../../docs/E2E_TEST_EVIDENCE_RULE.md). Synthetic laws validate
plumbing only; their text never proves real legal correctness.

## Evidence, feedback and remaining verification

Confirmed: original stakeholder request, the answer “SK+EU, rest per recommendation”,
and instruction to start implementation on 2026-10-15. These review the product
scope, not a legal classification or architecture approval. Repository evidence:
docs/SOFTWARE_REGULATORY_ASSESSMENT.md and app/software_assessment.
To verify, implementation owner: source coverage, runtime acceptance and security
review before release. No new product policy/ownership choice requires a BDR.
