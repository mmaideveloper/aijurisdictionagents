# ADR-001: Route speech-derived commands only through policy-enforced registered capabilities

## Record

- Status: Accepted
- Date: 2026-08-28
- Decision owner: Architecture authority (Unknown)
- Decision source: Requesting stakeholder instruction in Codex task, 2026-08-28
- Supersedes: None
- Superseded by: None
- Related artifacts: [`UC-001`](../use-cases/UC-001-speech-input-and-safe-command-execution.md), [`ADD-001`](../design/ADD-001-governed-speech-command-routing.md), target container and voice-command dynamic C4 views To create

## Context

UC-001 requires JurisDigta to distinguish spoken questions from commands, search a user-approved laptop location for a named contract, invoke official ORSR company verification, and suggest other relevant capabilities. Speech recognition and natural-language routing are probabilistic or pattern-based and may contain transcription errors, prompt injection, shell syntax, malicious filenames, or ambiguous intent. A laptop search also crosses from the JurisDigta platform into a privileged user-device boundary.

The repository already contains reviewed transcript flows, a structured voice intent endpoint, client intent mapping, and a basic registered tool collection. It also contains action-recognition code that can couple recognition to action-specific behavior. The existing evidence does not establish a uniform policy metadata and authorization boundary for every tool. A decision is needed before expanding voice commands so new capabilities do not introduce arbitrary code execution or inconsistent consent and confirmation behavior.

## Scope and Non-goals

- In scope: The execution boundary and authorization pattern for commands originating from speech or typed natural language; capability registration; structured requests; preview/confirmation; local and server capability enforcement; related-capability suggestions.
- Out of scope: Final STT provider, rules-versus-model classifier, local connector packaging/protocol, exact risk taxonomy, standing authorization policy, tool-specific business logic, and question/answer architecture.

## Decision Drivers

| Driver | Priority | Source/confidence |
|---|---|---|
| Prevent transcript, model output, or filenames from becoming executable code | Must | UC-001 FR-06, QA-02; Draft requirement |
| Enforce least privilege and user-approved scope for local files | Must | UC-001 FR-09/FR-10; Draft requirement |
| Provide consistent destination/risk disclosure and explicit authorization | Must | UC-001 FR-07/FR-09; Draft requirement |
| Ensure related tools never execute merely because they are relevant | Must | UC-001 FR-12/FR-13; Draft requirement |
| Support privacy-minimized traceability and at-most-once execution | Must | UC-001 FR-19, QA-04/QA-06; Draft requirement |
| Reuse and evolve existing intent endpoint and tool registry | Should | Repository evidence; Confirmed current state |
| Support server tools and a future local connector without duplicating policy in every client | Should | ADD-001; Conceptual proposal |
| Avoid blocking useful unsupported requests forever | Should | User goal and UC-001 | Confirmed/Draft |

## Options Considered

### Option A: Execute generated shell or code in a sandbox

- Description: Translate a natural-language command into PowerShell, Python, shell, or similar code and run it in a restricted process/container, with user confirmation.
- Advantages: Broad capability coverage; rapid support for novel file and OS tasks; can reuse operating-system utilities.
- Disadvantages/risks: The confirmation may not explain actual effects; sandbox and filesystem boundaries are difficult across desktop platforms; injection, traversal, data exfiltration, persistence, and supply-chain risks remain; generated commands are difficult to classify, audit, and test consistently; local user privileges may exceed intended scope.
- Driver assessment: Strong flexibility, but fails the primary least-privilege, predictable authorization, and assurance drivers for legal/confidential data.

### Option B: Route only to registered structured capabilities through a central policy gateway

- Description: Natural-language routing may propose a capability and structured slots. Only a versioned registered capability with declared schema, destination, permissions, side-effect level, confirmation policy, and executor can be authorized. The policy gateway validates user/context/scope and binds confirmation to the exact capability and policy versions. Local operations run through a dedicated least-privilege connector; no transcript-generated code executes.
- Advantages: Deny-by-default; bounded testable behavior; consistent preview/confirmation; capability-specific data minimization; centralized audit and replay protection; supports disabling/revoking a capability; aligns with current registry and structured intent direction.
- Disadvantages/risks: Higher integration effort per capability; cannot immediately satisfy arbitrary OS requests; catalog governance and metadata become security-critical; local connector and gateway availability add failure points; users may encounter unsupported requests.
- Driver assessment: Best fit for security, privacy, legal safety, traceability, interoperability, and incremental migration; reduced flexibility is explicit and manageable.

### Option C: Let each client or tool authorize and execute commands independently

- Description: Mobile, web, desktop, and each tool maintain their own intent, confirmation, permission, and execution logic.
- Advantages: Lower initial central-platform work; client-specific UX and use of native OS APIs; individual tools can evolve independently.
- Disadvantages/risks: Policy drift and bypass paths; duplicated consent and audit logic; inconsistent confirmation semantics; difficult conformance testing; related-tool suggestions may bypass original safeguards; security fixes require coordinated releases.
- Driver assessment: Supports short-term delivery but fails consistent policy, auditability, and cross-client assurance drivers.

## Decision

Select Option B: speech-derived and typed natural-language commands shall execute only through policy-enforced registered capabilities.

The binding boundaries, if accepted, are:

1. Speech recognition and intent classification may produce text, confidence, candidate intent, and structured slots, but never execution authority.
2. Raw transcript, model output, filenames, registry results, or tool output shall not be interpreted as shell, PowerShell, Python, SQL, or other executable code.
3. Every executable capability must have versioned schema, purpose, supported jurisdictions/clients, permissions, data destination, side-effect/risk classification, confirmation policy, timeout/cancellation behavior, result provenance, and owner. Missing or stale policy metadata makes it ineligible.
4. Authorization binds the authenticated user, purpose, structured inputs or their safe digest, scope grant, capability version, policy version, expiry, and idempotency key. Material change requires a new preview and confirmation.
5. Local-device operations execute only in a separately authenticated least-privilege connector. The initial contract-search capability is read-only and restricted to canonical user-approved roots; it returns filename/metadata before any separate open/upload action.
6. Server operations such as ORSR execute through registered adapters and disclose the external destination and result provenance.
7. Related capabilities are recommendations only. Each requires separate selection, preview, policy evaluation, and authorization.
8. Unsupported commands fail safely and may be captured as product demand without expanding privileges or improvising generated code.

This decision was accepted by the requesting stakeholder on 2026-08-28 and is binding for the related conceptual target design. Changes require a superseding ADR.

## Consequences

### Positive

- A single enforceable boundary separates uncertain natural language from privileged execution.
- Capability behavior, data use, destinations, and side effects become reviewable and testable.
- Clients can share policy semantics while retaining accessible platform-specific UI.
- Local search and external checks can use different executors without weakening authorization.
- Capability revocation, versioning, idempotency, denial, and privacy-safe audit are possible.
- GDPR minimization, transparency, purpose limitation, and EU AI Act human oversight can be applied per capability.

### Negative and trade-offs

- Every new command requires capability design, ownership, schema, policy metadata, tests, and review.
- Arbitrary laptop automation is intentionally unsupported.
- A catalog, authorization gateway, connector identity, and audit trail add components and operational cost.
- Existing recognition/execution paths must be inventoried and migrated to avoid bypasses.
- Stale catalog or policy state must fail closed, reducing availability.
- Confirmation can add friction; standing grants cannot be introduced without a separate business/governance decision.

## Security, Privacy, Safety, and Compliance

- Security/trust impact: Establishes the policy gateway as a privileged boundary and capability metadata as security-sensitive configuration. Requires strong administration, version integrity, replay protection, connector authentication, canonical path enforcement, scope tokens, rate/size limits, safe result handling, and threat modeling. It reduces but does not eliminate malicious tool implementation or supply-chain risk.
- Privacy/data-lifecycle impact: Enables purpose-specific minimization and destination disclosure. Raw audio remains transient by default; operational logs exclude audio/full transcripts. Local file metadata remains local unless separately authorized. Lawful bases, controller/processor roles, transfers, retention, deletion, subject rights, and DPIA applicability remain To verify.
- AI/automation/human-oversight impact: STT and model/rule routing are advisory and cannot authorize execution. Users review text and exact capability previews; legal-risk results remain reviewable and high-impact actions require separate human oversight. EU AI Act classification and deployer/provider obligations remain To classify.
- Clinical/legal-risk impact: Prevents unconfirmed speech from directly filing, signing, paying, deleting, uploading, or making final legal decisions. Official-source uncertainty and conflicts must be visible.
- Required review/approval: Architecture authority, product owner, security, privacy/DPO, legal/compliance, accessibility, client owners, and operations; authoritative decision source To obtain.

## Validation and Follow-up

| Action or validation | Owner | Due date | Tracking link |
|---|---|---|---|
| Review and approve/reject UC-001 scope and acceptance criteria | Product owner and stakeholders | Unknown | UC-001 |
| Decide business policy for local-device access, capability risk levels, and standing grants | Product/governance authority | Unknown | BDR To create |
| Produce threat model for gateway, catalog, local connector, and result handling | Security owner (Unknown) | Unknown | To create |
| Complete GDPR/DPIA and EU AI Act classification assessment | DPO/legal reviewer (Unknown) | Unknown | To create |
| Define versioned capability and authorization schemas, including replay/idempotency semantics | Architecture/API owners (Unknown) | Unknown | ADD-001 follow-up |
| Inventory and remove/bind all existing command execution paths to the gateway | Engineering owner (Unknown) | Unknown | Implementation task To create |
| Decide local connector deployment, authentication, signed update, revocation, and approved-root model | Architecture/security/client owners (Unknown) | Unknown | ADR To create |
| Create target C4 container and voice-command dynamic views | Architecture owner (Unknown) | Unknown | `$generate-c4` follow-up |
| Validate injection, scope escape, stale confirmation, duplicate execution, privacy logging, accessibility, and real synthetic E2E scenarios | QA/security/accessibility owners (Unknown) | Unknown | UC-001 AC-01–AC-15 |

## Evidence and Uncertainty

| Claim/question | Source | State |
|---|---|---|
| Reviewed transcript and current voice privacy controls exist. | `docs/mobile_voice_flow.md`, `docs/mobile_voice_compliance.md` | Confirmed |
| A structured voice intent endpoint exists for selected intents. | `docs/VOICE_INTENT_ROUTER.md` | Confirmed |
| Client intent mapping produces structured tool payloads and a generic fallback. | `mobile_app/lib/chat/intent_mapper.dart` | Confirmed |
| A registry contains ORSR and other legal verification tools. | `src/aijurisdictionagents/tools/registry.py` | Confirmed |
| Some audio action code couples recognition with action-specific behavior. | `src/aijurisdictionagents/agents/audio_action_tools.py` | Confirmed |
| Registry metadata currently satisfies the proposed complete policy contract. | Repository evidence reviewed 2026-08-28 | Not established; To verify |
| A constrained general local file-search connector exists. | Repository search and UC-001 evidence | Not found; proposed |
| Option B has authoritative approval. | Requesting stakeholder instruction in Codex task, 2026-08-28 | Confirmed |
