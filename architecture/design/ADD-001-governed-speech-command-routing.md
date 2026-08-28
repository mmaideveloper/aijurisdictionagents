# ADD-001: Governed speech question and command routing

## Record

- Status: Approved
- State described: Conceptual target
- Owner: Unknown
- Date: 2026-08-28
- Approval source: Requesting stakeholder instruction in Codex task, 2026-08-28
- Related use cases: [`UC-001`](../use-cases/UC-001-speech-input-and-safe-command-execution.md) (Draft)
- Related business decisions: To verify; a BDR is likely required for local-device access and standing authorization policy
- Related diagrams: Current [container view](../diagrams/jurisdigta/jurisdigta-current-container.mmd); target container and voice-command dynamic views To create
- Related decisions: [`ADR-001`](../decisions/ADR-001-route-speech-commands-through-policy-enforced-capabilities.md) (Accepted)

## Executive Summary

JurisDigta already supports reviewed speech transcripts, selected voice intents, and registered legal verification tools. The target design extends those parts into one governed path for both typed and spoken requests: input becomes reviewed text; questions enter the existing chat path; commands become structured capability requests; a policy gateway validates scope and authorization before a capability can execute.

The design deliberately separates recognition from authorization. Speech or model output may propose an intent, but cannot directly execute shell, PowerShell, Python, SQL, filesystem, or external-service operations. A capability catalog exposes only registered operations with schemas, permissions, data destinations, side-effect levels, and confirmation policy. A proposed local connector performs constrained read-only searches inside user-approved roots; ORSR remains a server-side external capability. Related capabilities are recommendations requiring separate selection and authorization.

Material uncertainty remains around client scope, local connector deployment and ownership, capability risk levels, lawful bases, retention, and service targets. Approval establishes the conceptual design direction but does not make it implementation-ready because UC-001 remains Draft and the documented blockers remain open.

## Scope and Non-goals

### In scope

- Common routing for reviewed typed and speech-derived text.
- Question/command classification and structured slot extraction.
- Capability discovery, policy evaluation, execution preview, confirmation, idempotent execution, result provenance, and privacy-safe audit.
- Integration with existing chat/question handling and ORSR tooling.
- Conceptual boundary for a constrained local contract-search connector.
- Suggestions for other relevant registered capabilities without automatic execution.
- Migration from current client-specific/rule-specific routing.

### Non-goals

- Choosing the final STT, intent-classification, transport, desktop packaging, or hosting technology.
- Granting arbitrary OS or code execution.
- Defining connectors for email, cloud drives, network shares, or unrestricted content indexing.
- Replacing existing case/chat, consent, identity, tool, or audit systems of record.
- Authorizing irreversible legal acts from voice alone.

## Architecture Drivers and Constraints

| Driver/constraint | Priority | Source | Confidence |
|---|---|---|---|
| Reviewed transcript must equal submitted normalized text | Must | UC-001 FR-02/FR-03 | Draft requirement |
| Transcript text must never be executed as code or shell | Must | UC-001 FR-06 and QA-02 | Draft requirement |
| Capability execution requires schema, permission, destination, risk, and confirmation metadata | Must | UC-001 FR-07/FR-09 | Draft requirement |
| Remote STT requires the applicable explicit consent; raw audio is transient by default | Must | `docs/mobile_voice_compliance.md` | Confirmed project policy |
| Local search is read-only and confined to user-approved roots | Must | UC-001 FR-10 | Draft requirement |
| Related capabilities are suggested but separately authorized | Must | UC-001 FR-12/FR-13 | Draft requirement |
| Duplicate recognition/confirmation must not duplicate execution | Must | UC-001 QA-06 | Draft requirement |
| Existing client-independent voice intent endpoint and tool registry should be evolved compatibly | Should | `docs/VOICE_INTENT_ROUTER.md`, `src/aijurisdictionagents/tools/registry.py` | Confirmed current state |
| Architecture must support mobile, web, and future local connector without client-specific safety policy | Should | UC-001 QA-08 | Draft requirement |
| Exact performance, availability, cost, residency, and retention targets are unknown | Must resolve | UC-001 open questions | Confirmed gap |

## Current-State Context

Mobile and web message mode can place STT output into a visible draft. The mobile `IntentMapper` maps recognized phrases to structured payloads and uses a generic fallback. The API exposes `POST /v1/voice/intent` for selected deterministic intents. The system core has a registry for several legal verification tools, including ORSR, while older audio action recognition combines recognition with action-specific behavior.

These parts demonstrate feasibility but leave policy distributed across clients and tools. The current tool definition/registry evidence does not establish complete authorization, side-effect, destination, or confirmation metadata. No general constrained laptop file-search connector was found. The current C4 container view models clients, API, workers, stores, model provider, and external checks but not a local-device capability boundary.

## Target Architecture

### Responsibilities and boundaries

| Element | Responsibility | Owner | Trust/data boundary | Evidence |
|---|---|---|---|---|
| JurisDigta client | Capture active speech, disclose processing mode, show/edit transcript, present preview/confirmation/result, provide typed fallback | Client application owner (Unknown) | User device and microphone permission boundary | Existing mobile/web behavior; confirmed/target extension |
| STT adapter | Convert one active audio segment to text and expose provider/runtime and confidence metadata; never authorize commands | Unknown | Device or disclosed remote processor boundary | Current voice docs; conceptual normalization |
| Request intake API | Accept reviewed text and context with correlation/idempotency identifiers | API owner (Unknown) | Authenticated client-to-platform boundary | Existing voice intent endpoint; target extension |
| Intent router | Classify question/command/ambiguous/unsupported and extract minimum structured slots; produce proposals only | Unknown | Untrusted natural-language to structured-data boundary | Existing deterministic router and intent mapper; target extension |
| Capability catalog | Publish versioned capability schemas, descriptions, destination, permissions, jurisdictions, side effects, confirmation policy, and availability | Tool/platform owner (Unknown) | Trusted configuration boundary | Existing registry is partial; target capability |
| Policy and authorization gateway | Validate identity, consent, scope grant, risk policy, required fields, capability version, and explicit confirmation; deny by default | Security/platform owner (Unknown) | Central execution authorization boundary | UC-001 and ADR-001; proposed |
| Execution orchestrator | Execute one authorized structured request idempotently, apply timeout/cancellation, and normalize status/provenance | Unknown | Trusted platform execution boundary | Conceptual target |
| Question/answer path | Process reviewed questions through existing chat/legal workflow and preserve human review | Existing API/chat owner (Unknown) | Existing legal AI boundary | Current architecture and UC-001 |
| Server capability adapters | Invoke registered server-side tools such as ORSR and return sourced normalized results | Tool owners (Unknown) | Platform-to-external-service boundary | Existing ORSR/tool registry; confirmed/target extension |
| Local capability connector | Perform only approved local operations, initially read-only filename/metadata search under approved roots; enforce canonical path and scope locally | Desktop/local connector owner (Unknown) | Separate user-device trust boundary; platform must not receive broader filesystem authority | Proposed; UC-001 |
| Audit/telemetry service | Record redacted decisions, grants, confirmations, capability/policy versions, status, and reviewer events | Operations/security owner (Unknown) | Restricted audit boundary | Existing telemetry plus target events |

### Interfaces and integrations

| Source | Destination | Purpose/data | Interface/protocol | Failure behavior |
|---|---|---|---|---|
| Client | STT adapter | Active audio segment, locale, consent state | Existing device/browser or configured remote STT interface | Block undisclosed/unauthorized remote upload; return typed fallback |
| Client | Request intake API | Reviewed normalized text, language, context, correlation and idempotency keys | Existing HTTPS API; exact target schema To define | Reject unauthenticated, malformed, oversized, or replayed requests |
| Request intake | Intent router | Reviewed text and minimum context | In-process/service boundary To decide | Return ambiguous/unsupported; never fall through to execution |
| Intent router | Capability catalog | Intent, jurisdiction, required capability traits | Structured catalog query; protocol To decide | Return no eligible capability and safe alternatives |
| Intent router | Question/answer path | Reviewed question and case context | Existing chat interface | Preserve existing error and human-review behavior |
| Client/request intake | Policy gateway | Selected proposal, confirmation token, scope grant, identity/consent context | Structured authorization contract To define | Deny closed on missing, expired, mismatched, or replayed authorization |
| Policy gateway | Execution orchestrator | Immutable authorized capability request with policy/capability versions | Internal contract To define | Do not execute if versions or scope changed after preview |
| Orchestrator | ORSR adapter | Minimum company name/IČO and locale/jurisdiction context | Existing official ORSR integration | Surface zero/multiple/error/staleness; do not guess |
| Orchestrator | Local connector | Authorized operation, approved root token, search term, limits | Mutually authenticated local protocol To decide | Deny offline, untrusted, expired, scope-escaping, or unsupported requests |
| Components | Audit/telemetry | Redacted decision and execution events | Existing telemetry/audit mechanisms To verify | Business action should fail closed if mandatory authorization audit cannot be recorded; operational telemetry may degrade without transcript leakage |

### Data architecture

| Data category | System of record | Processing purpose | Residency/retention/deletion | Access/audit |
|---|---|---|---|---|
| Raw audio | None by default | Transient recognition | Discard after recognition/failure; remote transfer only after applicable consent | No logs or audit payloads containing audio |
| Reviewed transcript/question | Existing case/chat store where submitted | User request and legal workflow | Existing case lifecycle and subject-rights controls; To verify | Existing authorized case access; exclude full text from operational logs |
| Structured command proposal | Pending-action store or client state To decide | Preview and confirmation | Short-lived; expire on cancel, logout, policy/capability change, or timeout | Bound to user, correlation, capability version, and purpose |
| Confirmation/scope grant | Existing consent/audit store or new authorization record To decide | Prove specific authorization | Retention and withdrawal/expiry To define | Restricted access; immutable event linkage without credentials |
| Capability metadata | Versioned catalog | Discovery and policy enforcement | Retain versions needed to interpret audit history | Administrative change audit required |
| Local file metadata | Prefer local connector/client; case store only after explicit user action | Display search matches | Session-only by default; content is not uploaded by search | Approved-root enforcement and redacted audit only |
| ORSR query/result | Existing tool/case/audit path To verify | Company verification and provenance | Case/freshness/retention rules To define | Source and retrieval time visible; representative data minimized |
| Execution audit metadata | Authorized audit store | Traceability and oversight | Retention/access/deletion policy To define | No raw audio, credentials, full transcript, or unrestricted paths |

### C4 views

- Current [container view](../diagrams/jurisdigta/jurisdigta-current-container.mmd): establishes existing clients, API, data stores, workers, and external services.
- Target container view To create with `$generate-c4`: answer “Where are transcript review, routing, policy authorization, server capabilities, and the local-device trust boundary enforced?”
- Voice-command dynamic view To create with `$generate-c4`: answer “Which checks and confirmations occur from spoken input through ORSR or local contract-search execution, including denial and cancellation?”

## Quality Attribute Scenarios

| Attribute | Stimulus and environment | Expected measurable response | Validation |
|---|---|---|---|
| Security | Reviewed transcript contains shell syntax, traversal, wildcard root, or prompt injection | Zero generated shell/code executions; only schema-valid registered capability requests can reach an executor | Unit/property tests plus synthetic local-connector E2E |
| Privacy | User selects remote STT without current applicable consent | Zero audio bytes sent; visible local/device or typed fallback | Network-boundary integration test and synthetic voice E2E |
| Authorization | Previewed request is confirmed after its scope, capability, or policy version changes | Request is denied and a new preview is required | Contract and replay tests |
| Isolation | Local search targets a path outside approved canonical roots through junction/symlink/traversal | Zero out-of-scope entries returned or opened | Windows/Linux connector security test matrix as applicable |
| Reliability | Duplicate final transcript or confirmation arrives for one action | Capability executes at most once | Idempotency integration test and audit assertion |
| Safety | Speech proposes write/delete/upload/submission/payment/signature action without approved high-impact policy | Zero side effect; user receives unsupported/confirmation/human-review response | Policy matrix tests and real user-visible E2E |
| Traceability | Authorized reviewer investigates completed command | Correlates intake, routing, preview, authorization, capability/policy version, result, and review state without raw audio/full transcript logs | Sanitized audit-manifest test |
| Performance | ORSR or local search exceeds an approved response threshold | Progress and cancellation become visible; timeout produces non-verified failure, not guessed result | Thresholds To define; latency/timeout tests |
| Accessibility | User operates voice flow with assistive technology | Listening, transcript, preview, confirmation, cancellation, and result have equivalent visual/accessible controls | Accessibility review and automated/manual checks |

## Security, Privacy, Safety, and Compliance

- Threat/trust boundaries: Treat microphone input, transcripts, model classifications, filenames, external responses, and connector results as untrusted. Central policy authorization, capability catalog administration, local connector identity, approved-root tokens, and audit access are privileged boundaries. Threat analysis must cover prompt injection, command injection, path traversal, junction/symlink escape, confused deputy, replay, stale confirmation, capability substitution, excessive result disclosure, malicious filenames/content, SSRF through tool parameters, and audit leakage.
- GDPR safeguards: Purpose-specific disclosure and remote-STT consent per current policy; minimum utterance and slots; no raw-audio retention by default; local-first metadata search; explicit destinations; documented controller/processor roles, transfers, retention, deletion, access, correction, restriction, portability, withdrawal, and DPIA applicability before approval.
- EU AI Act safeguards: Classification is To verify. Preserve provider/runtime disclosure, accuracy limitations, logs proportionate to purpose, accessible transcript review, ability to cancel/override, and meaningful human oversight for legal-risk outcomes. Classification output cannot itself authorize execution.
- Clinical/legal-risk safeguards: Results remain drafts/evidence for review, official-source uncertainty is visible, and no filing, signature, payment, deletion, or external legal submission occurs solely from unconfirmed speech.
- Compliance blockers: Lawful bases and roles; remote processor/transfer assessment; local connector data scope; capability risk and confirmation taxonomy; retention/access policies; EU AI Act classification; human approval authority; and DPIA/security review applicability remain unresolved.

## Deployment and Operations

- Environments/topology: Existing web/mobile clients and API remain. Server capability adapters execute within the controlled backend boundary. A local connector, if approved, runs in the user-device boundary and receives narrowly scoped requests; packaging, protocol, authentication, update, and revocation are To decide. Test precedes production.
- Observability and privacy-safe logging: Record correlation/idempotency identifiers, client/runtime class, language, intent, capability/policy version, risk level, consent/confirmation outcome, timing, result status, denial reason, and human-review state. Exclude audio, credentials, unrestricted absolute paths, file contents, and full transcripts. Redact structured slots according to capability policy.
- Availability, recovery, and continuity: Targets are To verify. Fail closed for authorization/catalog uncertainty. Permit typed questions when STT fails; preserve editable drafts locally where safe; show unavailable capabilities without inventing results. No automatic retry may duplicate side effects.
- Operational ownership and support: Product, client, API/platform, security, privacy/legal, capability, local connector, and operations owners are Unknown and must be assigned before implementation readiness.

## Delivery, Migration, and Rollback

1. Define and approve capability metadata, risk taxonomy, authorization contract, retention, and owner model; keep current voice execution behavior unchanged.
2. Add catalog-backed discovery and dry-run previews behind a disabled-by-default feature flag; compare routing with current deterministic behavior without executing new capabilities.
3. Route existing low-risk intents, beginning with ORSR, through the gateway with explicit preview/confirmation and idempotent audit; retain the current endpoint contract through an adapter.
4. Add related-capability suggestions as non-executable recommendations and measure relevance/decline rates using privacy-safe events.
5. Build and security-test a local read-only filename/metadata connector only after its BDR, threat model, protocol decision, and ownership are approved; pilot with synthetic roots.
6. Expand clients/capabilities incrementally after real local E2E, accessibility, compliance, and operational review.

- Compatibility/data migration: Preserve existing text/chat paths and adapt existing voice intent payloads. Version capability and policy contracts. Existing consent and case records are reused only after schema/purpose compatibility is verified; do not silently reinterpret old consent as local-file authorization.
- Rollback trigger and procedure: Disable the affected capability or gateway route on authorization bypass, duplicate execution, scope escape, sensitive logging, material routing regression, or provider-policy failure. Revert clients to reviewed text submission and existing question handling; revoke connector tokens/grants; preserve sanitized incident evidence. Database rollback needs depend on the eventual authorization/audit schema and must be defined before migration.

## Decisions and Alternatives

| Decision topic | ADR | Status | Design impact |
|---|---|---|---|
| Execution boundary for speech-derived commands | [`ADR-001`](../decisions/ADR-001-route-speech-commands-through-policy-enforced-capabilities.md) | Accepted | Introduces registered structured capabilities and centralized policy authorization; excludes transcript-generated OS/code execution |
| Local connector deployment, authentication, and update model | To create after product/security direction | Not yet decided | Determines device trust boundary and operational ownership |
| Capability risk/confirmation taxonomy and standing grants | BDR likely, then ADR if technical choice remains | Not yet decided | Determines UX and authorization policy |
| Intent classification strategy (rules, model, hybrid) | To create only if independently material | Not yet decided | Must remain proposal-only and unable to authorize execution |
| Authorization/audit persistence model | To create after retention and ownership are known | Not yet decided | Determines replay protection, evidence, and deletion behavior |

## Risks, Assumptions, and Open Questions

| Item | Type/state | Impact | Mitigation/owner |
|---|---|---|---|
| UC-001 has not been reviewed or approved | Risk/blocker | Scope and acceptance may change materially | Stakeholder review; product owner |
| Users may interpret voice as authorization | Risk | Unintended disclosure or side effect | Separate transcript send from capability preview/confirmation; UX/accessibility review |
| Local connector creates a privileged endpoint on user devices | Risk | Device data exposure or code execution | Dedicated threat model, least privilege, signed updates, mutual authentication, approved roots; owners To assign |
| Catalog metadata may be missing, stale, or manipulated | Risk | Incorrect policy or destination disclosure | Version/sign/authorize changes; deny unclassified or mismatched capabilities |
| Model/rule routing may misclassify names, negation, amounts, or commands | Risk | Wrong question/action | Editable transcript, proposal-only routing, confidence/ambiguity handling, exact-slot validation |
| Suggesting many related tools may manipulate or overwhelm users | Risk | Unnecessary processing and consent fatigue | Relevance threshold, explanation, ranking limits, separate opt-in; product owner |
| Filename/content search scope for first release | To verify | Changes privacy, performance, indexing, and connector design | Draft recommends filename/metadata only; product/security/privacy decision |
| Supported clients, OSs, languages, service levels, and owners | Unknown | Blocks deployment and operational design | Assign and document before implementation |
| Lawful bases, processor roles/transfers, retention, AI classification, DPIA | To verify/blocker | Compliance approval unavailable | DPO/legal review |
| Existing tool paths use inconsistent naming and recognition/execution coupling | Risk | Migration complexity and bypass paths | Inventory all invocations; adapter first; remove bypass only after conformance tests |

## Verification and Implementation Readiness

- [ ] Reviewed use cases and acceptance criteria are linked.
- [ ] Required C4 views are linked and evidence-backed.
- [x] Binding decisions are accepted and reconciled.
- [ ] Compliance blockers are closed.
- [x] Test, migration, observability, rollback, and documentation work are outlined; measurable service targets and final schemas remain open.

Readiness: Not ready. Approval confirms the conceptual design and ADR-001, but UC-001 is Draft, target C4 views are missing, and material compliance/ownership decisions remain open.

## Evidence

| Claim | Source | Confidence |
|---|---|---|
| Visible reviewed STT message flow exists for mobile/web. | `docs/mobile_voice_flow.md` | Confirmed repository evidence |
| Remote audio consent, minimization, deletion, transparency, and oversight baseline exists. | `docs/mobile_voice_compliance.md` | Confirmed repository evidence |
| A client-independent structured voice intent endpoint exists for selected intents. | `docs/VOICE_INTENT_ROUTER.md` | Confirmed repository evidence |
| Mobile maps known voice intents to tool payloads and a generic fallback. | `mobile_app/lib/chat/intent_mapper.dart` | Confirmed code evidence |
| Registered legal tools include official ORSR company checking. | `src/aijurisdictionagents/tools/registry.py`, `docs/SLOVAK_COMPANY_CHECKS.md` | Confirmed code/document evidence |
| Current audio recognition includes paths that couple recognition with action-specific behavior. | `src/aijurisdictionagents/agents/audio_action_tools.py` | Confirmed code evidence |
| Current C4 view contains clients, API, stores, workers, model provider, and external checks but no local connector boundary. | `architecture/diagrams/jurisdigta/jurisdigta-current-container.mmd` | Confirmed architecture evidence |
| General constrained laptop contract-search capability was not found. | Repository search performed 2026-08-28 | Not found; conceptual target |
