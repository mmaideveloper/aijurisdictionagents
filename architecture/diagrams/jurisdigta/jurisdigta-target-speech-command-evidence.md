# JurisDigta target speech-command C4 evidence

## Record

- State: Conceptual target
- Views: Container and dynamic
- Date: 2026-08-28
- Related artifacts: [`UC-001`](../../use-cases/UC-001-speech-input-and-safe-command-execution.md), [`ADD-001`](../../design/ADD-001-governed-speech-command-routing.md), [`ADR-001`](../../decisions/ADR-001-route-speech-commands-through-policy-enforced-capabilities.md)
- Editable sources: [`jurisdigta-target-speech-command-container.mmd`](jurisdigta-target-speech-command-container.mmd), [`jurisdigta-target-speech-command-dynamic.mmd`](jurisdigta-target-speech-command-dynamic.mmd)

## Stakeholder questions

- Container view: Where are transcript review, routing, policy authorization, server capabilities, and the local-device trust boundary enforced?
- Dynamic view: Which checks and confirmations occur from spoken input through ORSR or approved-root contract search, including denial and cancellation?

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
| User reviews an editable transcript before ordinary submission | `docs/mobile_voice_flow.md`, UC-001 FR-02/FR-03 | Existing behavior; confirmed for documented mobile/web flow |
| Device/browser or disclosed remote STT adapter | `docs/mobile_voice_flow.md`, `docs/mobile_voice_compliance.md` | Existing modes; exact cross-client implementation varies |
| Remote audio upload requires applicable consent and raw audio is transient by default | `docs/mobile_voice_compliance.md` | Confirmed project policy |
| Client-independent request/intent API | `docs/VOICE_INTENT_ROUTER.md`, `api/aijuristiction-api/app/voice_intent_api.py` | Existing, limited intents |
| Existing question/chat path | Current container view and API chat source | Confirmed current boundary |
| Mobile structured tool invocation payload and generic fallback | `mobile_app/lib/chat/intent_mapper.dart` | Confirmed code |
| Existing registered ORSR and verification tools | `src/aijurisdictionagents/tools/registry.py`, `docs/SLOVAK_COMPANY_CHECKS.md` | Confirmed code/documentation |
| Capability catalog with policy-complete metadata | ADD-001, ADR-001 | Proposed |
| Central policy and authorization gateway | ADD-001, ADR-001 | Approved design / accepted decision; not implemented |
| Idempotent execution orchestrator | ADD-001, UC-001 QA-06 | Proposed |
| Local read-only approved-root connector | UC-001 FR-10, ADD-001 | Proposed; no implementation found |
| ORSR external interaction over HTTPS | Existing ORSR tool/documentation | Confirmed current integration |
| Separate preview/confirmation and related-tool authorization | UC-001 FR-09/FR-12/FR-13, ADR-001 | Required target behavior |
| Authorization/audit persistence | ADD-001 | Conceptual; exact store/schema To decide |

## Assumptions

- Mobile and web remain the first documented client types; a local connector is a separate runnable boundary rather than unrestricted backend filesystem access.
- Filename/metadata-only search is the first local-search increment; opening or uploading content is a separate capability.
- Existing HTTPS client/API and ORSR interactions remain; the local connector protocol is intentionally not selected.

## Unresolved questions

- Which clients, desktop operating systems, and approved folder types are in the first release?
- Where does the local connector run, how is it authenticated/updated/revoked, and who operates it?
- What capability risk taxonomy, standing grants, authorization record retention, and audit availability rules apply?
- Are the intent router, catalog, policy gateway, and executor modules within one API deployment or separately deployable containers?
- What are the final controller/processor roles, remote STT transfer safeguards, DPIA result, and EU AI Act classification?

## Validation

- Relative artifact links: Passed on 2026-08-28.
- Mermaid source/static review: Passed; both files use one abstraction level, directional labeled relationships, explicit target/proposal notation, and no secrets or real personal data.
- Renderer/SVG: Pending. No local `mmdc` executable was installed, and retrieval of `@mermaid-js/mermaid-cli` failed with `UNABLE_TO_VERIFY_LEAF_SIGNATURE`. TLS verification was not bypassed. Render both sources and visually inspect the SVGs before implementation readiness or publication.
