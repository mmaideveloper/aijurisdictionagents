# UC-004: Prepare using explicitly approved private question banks

## Record
- Status: Reviewed
- Date: 2026-10-18
- Owner: Product owner
- Stakeholders: existing administrators, registered learners
- Review source: [#924](https://github.com/mmaideveloper/aijurisdictionagents/issues/924), owner confirmation in the originating conversation (2026-10-18).
- Related: [ADD-003](../design/ADD-003-private-study-banks.md), [ADR-004](../decisions/ADR-004-explicit-bank-grants.md), [#841](https://github.com/mmaideveloper/aijurisdictionagents/issues/841).

## Outcome, actors and scope
Confirmed: public visitors see bank metadata; registered learners request access; existing administrators approve a user AND individually selected banks. A learner can privately save searched/manually selected questions and practise them on desktop/mobile. Administration belongs exclusively to the tests site. Native applications, official medical exam scoring and publication of unlicensed book content are excluded.

## Flows and requirements
1. FR-01: Visitor sees published descriptions, registers/signs in centrally and requests a bank.
2. FR-02: Administrator reviews request, enables the user and selects explicit bank grants. Selecting all does not grant future banks.
3. FR-03: Learner filters approved bank questions (OR within tag group, AND across groups), saves a private collection and starts learning.
4. FR-04: Administrator uploads a PDF or ordered PNG/JPEG pages, reviews faithful source-grounded extraction, corrects uncertainty and installs inactive questions before explicitly activating them.
5. FR-05: Administrator edits versioned questions/answers and tags; requested AI tagging uses a supplied rubric, presents rationale/uncertainty, and requires approval.

Failures: missing/revoked grants deny every subsequent protected request including stale sessions. Expiry blocks new practice/submission while permitted historical reading remains. Disabled questions block submissions and require saved-set correction. Concurrent question edits conflict instead of overwriting. Failed processing is unscored/retryable and never invents source answers.

## Data and governance pre-check
Personal data: central account identifier, private selections/attempts and approval metadata; administrator-only email lookup is transient, not copied into tests storage. Do not send learner identity/history to extraction/tagging. Lawful basis and AI-risk classification remain To verify by the operator; this change is study assistance and must not be presented as admission/certification decisions or medical advice.

Proposed operational defaults: job/source drafts 30 days, pending/rejected/revoked requests 90 days, metadata audits and existing attempts 12 months; collections/grants until deletion or account removal. Preserve question revisions needed by attempts and do not retain account details in revision content. Explain processing and retention in UI/docs. Administrators retain meaningful review authority. Rights for purchased LF UK material remain Unknown: synthetic/authorized-content implementation is permitted, purchased-content publication remains gated.

## Acceptance and evidence
- QA-01: Three synthetic learners demonstrate firearms-only, medical-only and both-bank grants with direct API negative tests.
- QA-02: Revocation denies existing sessions and foreign collections; role demotion blocks administration/jobs.
- QA-03: Real local PostgreSQL, actual services and configured real model validate PDF/image import, tagging and practice; final mobile/desktop screenshots plus sanitized manifests follow the repository evidence rule.
- QA-04: No Q&A/source content is publicly readable; no management screen is added to agents administration.

## Open items and feedback
Confirmed by owner: PDFs and PNG/JPEG scans are supported without knowing the final book layout. Exact medical scoring is deferred. Content rights/curriculum applicability require owner review before using purchased data; use explicit admin-provided tag rubric meanwhile. Retention defaults are documented implementation choices, not a legal compliance approval.
