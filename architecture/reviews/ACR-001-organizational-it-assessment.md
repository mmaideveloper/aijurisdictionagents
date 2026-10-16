# ACR-001: Organizational IT assessment conformance and security review

- Status: Complete for implementation review; no release or legal approval inferred.
- Date: 2026-10-15; reviewer: Codex implementation review; accountable release/legal owners: To verify.
- Baseline: stakeholder-confirmed scope in [#909](https://github.com/mmaideveloper/aijurisdictionagents/issues/909),
  root AGENTS.md, [UC-003](../use-cases/UC-003-organizational-it-legal-analysis.md).
- Advisory design: [ADD-002](../design/ADD-002-organizational-it-assessment.md), In Review;
  [ADR-003](../decisions/ADR-003-share-assessment-controls.md), Proposed, not an approved baseline.
- Instructions/provenance: jurisdigta profile in architecture/toolkit-profile.yaml;
  pinned toolkit architecture-change, generate-use-case, generate-add, generate-adr,
  review-architecture-conformance and security-review guidance. No separate toolkit
  project key or external profile was supplied.

## Requirement and evidence matrix

| Requirement / boundary | Evidence | Result |
|---|---|---|
| Distinct organizational IT case and SK/EU scope | case_types/seed.py; organizational_it.py; real web and chat intake | Conformant |
| Czech original retained as unsupported national-law scenario | jurisdiction_blockers; unit matrix; ignored cz-boundary.jpg | Conformant |
| Shared API/web/simulator result and review contract | it_api.py delegates to shared case-private assessment; it_conversation.py uses same engine | Conformant |
| Case authentication and isolation | require_review_user; shared case access/write checks; authenticated API tests | Conformant |
| Account privacy policy plus case acknowledgment | existing PrivacyControls routing and shared create; observed real policy denial until synthetic account consent was seeded | Conformant |
| Source and document reference integrity | validate_output, exact provision-reference guard, original document excerpts, bounded retry and explicit incomplete results | Conformant for structural references; semantic legal support remains Not verifiable automatically |
| Distinguish law, policy, contract and recommendation | Action.basis; ChecklistItem.category; policy-excerpt and mismatched-article tests | Conformant |
| No automatic certification or document generation | human-review warnings; action state/evidence controls; legacy draft/export guards and UI tests | Conformant |
| Conditional document recommendations | validated model checklist or recommended working-record fallback; real document-recommendations.jpg | Conformant |
| Case retention/deletion and optimistic revisions | existing assessment store reused; deletion and idempotency tests | Conformant |
| Source traceability through real local services | actual Azure Foundry gpt-4o-mini, migrated local API/laws PostgreSQL, direct MCP source check, real frontend-created case and persisted grounded citations | Conformant for synthetic integration acceptance |
| Unavailable selected model | real API request, actual default real route, visible frontend disclosure in fallback-state.jpg | Conformant |

## Focused security review

Assets are private case facts/policies and source/model provenance. New entry points
are bounded organizational intake and case-private assessment resources. They use
the existing device identity, case owner/write-window checks and authorized reviewer
controls; no new privilege, cloud endpoint, credential type or database is introduced.
Public law queries contain fixed topics rather than case content. External model
processing is checked by existing account privacy policy and explicit case acknowledgment.

STRIDE-informed checks: spoofing/access is covered by inherited authenticated tests;
tampering uses revision and evidence hash checks; reference injection uses exact
IDs/excerpts and named-provision validation; disclosure is limited by private model
I/O and fixed public queries; bounded inputs/retries constrain resource use; trace
metadata records actual route, graph and prompt versions. React escapes generated
text and source URLs are restricted by the existing official-host retrieval filter.
These checks are not penetration testing or certification.

## Validation, limitations and follow-up

API suite: 795 tests, 790 passed and 5 prerequisite-dependent skips; zero failures/errors.
API ruff/mypy gate passed. Frontend production build, lint (existing warnings only),
and all 206 frontend tests passed. Minimal demo passed.
Sanitized evidence: ignored runs/e2e/issue909/result-manifest.json and screenshots.
Source run identifiers in the manifest match direct MCP and persisted API citations.

Residual risks, owner product/legal reviewer: the law fixture is explicitly synthetic;
it verifies plumbing and source identity, not substantive legal correctness, national
law completeness or actual organizational compliance. Named-provision checks do not
establish semantic entailment of every generated sentence. Human review and visible
coverage limitations remain mandatory. Missing policies are not proven violations;
actions remain preliminary, unverified and evidence-seeking. No residual risk has
been formally accepted on behalf of the user.

Implementation review can proceed. Production release and reliance on an individual
assessment require the normal authorized review and real legal-source coverage checks.
The synthetic case and derived IT assessments were soft-deleted and the deletion
verified. Automatic approval review blocked the command removing the two isolated
test databases and runtime files, reporting only "blocked by policy". Their final
cleanup remains pending; no permanent deletion or complete-cleanup claim is made.
Clean the remaining task-created synthetic storage after capture; ignored evidence expires within
seven days under docs/E2E_TEST_EVIDENCE_RULE.md. There are no infrastructure or health
endpoint changes requiring new production setup or monitoring configuration.
