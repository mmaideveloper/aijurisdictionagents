# JurisDigta target speech-command C4 evidence

## Record

- State: Conceptual target
- Views: Container and dynamic
- Date: 2026-08-28
- Related artifacts: [`UC-001`](../../use-cases/UC-001-speech-input-and-safe-command-execution.md), [`ADD-001`](../../design/ADD-001-governed-speech-command-routing.md), [`ADR-001`](../../decisions/ADR-001-route-speech-commands-through-policy-enforced-capabilities.md)
- Editable sources: [`jurisdigta-target-speech-command-container.mmd`](jurisdigta-target-speech-command-container.mmd), [`jurisdigta-target-speech-command-dynamic.mmd`](jurisdigta-target-speech-command-dynamic.mmd)

## Stakeholder questions

- Container view: Where are transcript review, routing, policy authorization, server capabilities, and the local-device trust boundary enforced?
- Dynamic view: Which checks and confirmations occur from spoken input through ORSR or session-scoped browser folder search, including denial and cancellation?

## Legend and notation

- Blue elements are confirmed existing responsibilities or containers.
- Yellow dashed elements/relationships are conceptual proposals.
- Gray elements are external systems.
- Dotted arrows indicate optional or proposed boundary crossings.
- Labels identify regulated or confidential data only where repository evidence supports it.
- Technology/protocol is omitted or marked To decide where the repository has not established it.

## Evidence table

| Element or relationship | Source | Confidence/state |
|---|---|---|
| User reviews an editable web transcript before ordinary submission | `frontend/aijurisdictionfronend/src/pages/Home.tsx`, `frontend/aijurisdictionfronend/README.md` | Confirmed existing web behavior |
| Browser-native STT adapter | `frontend/aijurisdictionfronend/src/audio/speechToText.ts` | Confirmed existing web behavior |
| Remote audio upload requires applicable consent and raw audio is transient by default | `docs/mobile_voice_compliance.md` | Confirmed project policy |
| Client-independent request/intent API | `docs/VOICE_INTENT_ROUTER.md`, `api/aijuristiction-api/app/voice_intent_api.py` | Existing, limited intents |
| Existing question/chat path | Current container view and API chat source | Confirmed current boundary |
| Authenticated assistant routing at `agent.jurisdigta.eu` | `frontend/aijurisdictionfronend/src/routing.ts`, frontend README | Confirmed code/documentation |
| Existing registered ORSR and verification tools | `src/aijurisdictionagents/tools/registry.py`, `docs/SLOVAK_COMPANY_CHECKS.md` | Confirmed code/documentation |
| Capability catalog with policy-complete metadata | ADD-001, ADR-001 | Proposed |
| Central policy and authorization gateway | ADD-001, ADR-001 | Approved design / accepted decision; not implemented |
| Idempotent execution orchestrator | ADD-001, UC-001 QA-06 | Proposed |
| Browser session-scoped filename/metadata search | Stakeholder clarification 2026-08-30, GitHub issue #695 | Confirmed target scope; not implemented |
| ORSR external interaction over HTTPS | Existing ORSR tool/documentation | Confirmed current integration |
| Separate preview/confirmation and related-tool authorization | UC-001 FR-09/FR-12/FR-13, ADR-001 | Required target behavior |
| Authorization/audit persistence | ADD-001 | Conceptual; exact store/schema To decide |

## Assumptions

- The first release targets only the authenticated React assistant at `agent.jurisdigta.eu`.
- Browser-selected, session-scoped filename/metadata search is the first local-search increment; folder handles are not persisted, and opening, reading, or uploading content is out of scope.
- Existing HTTPS client/API and ORSR interactions remain; local filename/metadata search executes inside the browser session after user folder selection and gateway authorization.

## Unresolved questions

- Which supported browsers expose the required directory-selection API, and what exact manual fallback is presented elsewhere?
- Does ADR-001 require a superseding ADR because the first release uses an in-browser capability rather than a separately installed connector?
- What capability risk taxonomy, standing grants, authorization record retention, and audit availability rules apply?
- Are the intent router, catalog, policy gateway, and executor modules within one API deployment or separately deployable containers?
- What are the final controller/processor roles, remote STT transfer safeguards, DPIA result, and EU AI Act classification?

## Validation

- Relative artifact links: Passed on 2026-08-28.
- Mermaid source/static review: Passed; both files use one abstraction level, directional labeled relationships, explicit target/proposal notation, and no secrets or real personal data.
- Renderer/SVG: Pending. No local `mmdc` executable was installed, and retrieval of `@mermaid-js/mermaid-cli` failed with `UNABLE_TO_VERIFY_LEAF_SIGNATURE`. TLS verification was not bypassed. Render both sources and visually inspect the SVGs before implementation readiness or publication.
