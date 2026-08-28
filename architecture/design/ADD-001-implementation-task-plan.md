# ADD-001 implementation task plan

## Record

- Status: Draft task preparation
- Date: 2026-08-28
- Source: [`UC-001`](../use-cases/UC-001-speech-input-and-safe-command-execution.md), [`ADD-001`](ADD-001-governed-speech-command-routing.md), [`ADR-001`](../decisions/ADR-001-route-speech-commands-through-policy-enforced-capabilities.md), and target [C4 evidence](../diagrams/jurisdigta/jurisdigta-target-speech-command-evidence.md)
- GitHub creation: Not yet authorized; conversational request requires explicit confirmation before issue/project writes
- Delivery rule: Each task must use a separate branch/worktree and may start only after its dependencies and blockers are closed

## Recommended delivery order

| Order | Task | Project | Readiness | Depends on |
|---|---|---|---|---|
| 1 | T1 — Resolve governance, risk taxonomy, and local-access product policy | Backend/system project 5 | Not Ready Yet | Stakeholder decisions |
| 2 | T2 — Extend the capability definition and registry with enforceable policy metadata | Backend/system project 5 | Ready after T1 policy contract | T1 |
| 3 | T3 — Implement the API policy/authorization gateway, idempotent executor, and redacted audit | Backend/system project 5 | Ready after T1/T2 and retention decision | T1, T2 |
| 4 | T4 — Migrate ORSR voice/company verification and related-capability discovery through the gateway | Backend/system project 5 | Ready after T3 | T3 |
| 5 | T5 — Design and implement the constrained local contract-search connector | Backend/system project 5 | Not Ready Yet | T1, separate connector ADR/threat model, T3 |
| 6 | T6 — Implement mobile transcript preview, command authorization, and result UX | Backend/system project 5 | Ready after API contract is stable | T3, T4; T5 for local search |
| 7 | T7 — Implement web/chat-simulator transcript preview, command authorization, and result UX | Frontend project 6 | Ready after API contract is stable | T3, T4; T5 for local search |
| 8 | T8 — Complete real local E2E, security, privacy, accessibility, operations, and rollout evidence | Backend/system project 5 with frontend coordination | Ready after feature tasks | T3–T7 |

## T1 — Resolve governance, risk taxonomy, and local-access product policy

### Prepared Technical Details

- Problem / idea source: ADD-001 is approved but not implementation-ready because UC-001 remains Draft and local-device scope, lawful bases, retention, risk levels, standing grants, ownership, and regulatory classification are unresolved.
- Proposed approach: Review/approve UC-001; create the required BDR for local-device access and standing authorization; define capability classes (read-only local, read-only external, disclosure, write, destructive, legal submission), confirmation rules, prohibited actions, controller/processor roles, retention/access matrix, DPIA outcome, EU AI Act classification, supported clients/OS/languages, and named operational owners.
- GDPR/EU AI Act: This task owns the unresolved governance evidence; it must not use real customer data.
- Data/storage impact: Documentation only; no runtime schema or secrets.
- Acceptance criteria:
  - [ ] UC-001 has an authoritative review state and resolved first-release scope.
  - [ ] A BDR records local-device access, search breadth, related-tool suggestion policy, and standing-grant policy.
  - [ ] Risk/confirmation, retention/access, controller/processor, transfer, DPIA, AI classification, and human-oversight decisions are documented.
  - [ ] Product, security, privacy/legal, architecture, client, connector, and operations owners are assigned.
- Test plan: Architecture/governance quality review and traceability check against UC-001 AC-01–AC-15.
- Documentation/minimal example: Update UC/ADD/ADR/C4 as decisions change; minimal runnable code example is not applicable to this documentation-only task.
- Readiness: `Not Ready Yet`; requires stakeholder answers listed below.

## T2 — Extend capability definitions and registry with policy metadata

### Prepared Technical Details

- Problem / idea source: `ToolDefinition` and `ToolRegistry` do not establish the complete metadata contract required by ADR-001.
- Likely components: `src/aijurisdictionagents/tools/base.py`, `src/aijurisdictionagents/tools/registry.py`, registered tool definitions, registry/tool tests, package version, documentation, and `examples/minimal_demo.py`.
- Proposed approach: Add typed, versioned capability metadata for input schema, purpose, jurisdiction/client support, data destination, permission class, side-effect/risk class, confirmation policy, timeout/cancellation, provenance, availability, and owner identifier. Reject incomplete/unclassified executable registrations. Keep secrets and user data out of metadata.
- Error/fallback: Catalog lookup returns no eligible capability on invalid/stale metadata; it never falls through to arbitrary execution.
- GDPR/EU AI Act: Metadata exposes destination, purpose, and oversight requirements; no personal data persists.
- Acceptance criteria:
  - [ ] All executable default tools have valid versioned metadata and deterministic validation.
  - [ ] Incomplete, duplicate, unknown-risk, or schema-invalid capabilities are ineligible and produce safe diagnostics.
  - [ ] Discovery filters by intent traits, jurisdiction, client, and availability without exposing unauthorized tools.
  - [ ] Existing tool execution remains compatible through an explicit adapter until T3 migration.
- Tests: Typed unit/property tests for validation, versioning, filtering, duplicate names, serialization, and redacted errors.
- Documentation/minimal example: Update tool registry docs and `python examples/minimal_demo.py` to list policy-safe capability summaries.
- Versioning: Bump system-core revision under `src/`.
- Readiness: Ready only after T1 fixes the metadata taxonomy.

## T3 — Implement policy gateway, authorization records, idempotent execution, and audit

### Prepared Technical Details

- Problem / idea source: Current `POST /v1/voice/intent` can combine classification and selected execution; ADR-001 requires proposal and authority to be separate.
- Likely components: `api/aijuristiction-api/app/voice_intent_api.py`, `voice_intent.py`, new capability-policy/orchestration modules, API stores/migrations, consent/audit services, API tests, system-core interfaces, `.env.example` only if a genuinely new setting is required.
- Proposed approach: Introduce versioned propose/authorize/execute contracts. Bind authorization to user, purpose, capability/policy versions, safe input digest, scope, expiry, and idempotency key. Revalidate immediately before execution. Persist redacted authorization/denial/outcome events and enforce at-most-once execution. Preserve existing endpoint behavior through a versioned compatibility path that cannot bypass the gateway.
- Error/fallback: Deny closed on missing/expired/replayed/mismatched authorization, unavailable catalog/audit dependency, changed policy, or unsupported capability; ordinary questions and typed fallback remain available.
- Data/storage: New PostgreSQL migration likely required for short-lived proposals/authorizations and audit linkage; exact retention/deletion follows T1. SQL assets stay under the API migration layout and runtime data remains under `runs/storage/...`.
- Acceptance criteria:
  - [ ] Classification produces no execution authority.
  - [ ] Exact preview and confirmation are cryptographically/unambiguously bound to one request and expire safely.
  - [ ] Duplicate transcript/final/confirmation events execute at most once.
  - [ ] Mandatory authorization audit failure blocks execution without logging full transcript or secrets.
  - [ ] Question flow and old supported clients remain compatible without bypassing policy.
- Tests: Unit/state-machine, API contract, migration, replay/concurrency, stale-version, consent, audit-redaction, failure-injection, and PostgreSQL integration tests.
- Documentation/minimal example: Update voice API, privacy/audit docs, migrations, and `python examples/minimal_demo.py` with proposal/confirmation/execution flow.
- Versioning/validation: Bump API and system-core revisions as applicable; run API ruff, mypy, unit tests, and repository validation gates.
- Readiness: Ready after T1/T2 and audit retention/access decisions.

## T4 — Route ORSR and related company capability suggestions through the gateway

### Prepared Technical Details

- Problem / idea source: ORSR exists, but company voice commands and additional related-tool suggestions must use the accepted authorization boundary.
- Likely components: ORSR tool definition, `api/.../chat/country_services/slovakia.py`, voice intent mapping, catalog discovery/ranking, API/core tests, company-check docs, and focused demo.
- Proposed approach: Register official ORSR lookup with complete metadata; map company queries to a proposal; require the T1 policy confirmation; return source/retrieval time and zero/one/multiple status. Rank a bounded number of other eligible company capabilities by declared traits and explain relevance, destination, data, and risk. Suggestions never execute automatically.
- GDPR/EU AI Act: Minimize company/representative data, record source freshness, preserve ambiguity and human review, and avoid profiling claims unsupported by an approved capability.
- Acceptance criteria:
  - [ ] Exact company name/IČO remains intact from reviewed transcript to structured slot.
  - [ ] ORSR runs only after valid authorization and returns sourced, time-stamped match status.
  - [ ] Ambiguous matches request a stronger identifier and block downstream legal reliance.
  - [ ] Related suggestions are bounded, policy-eligible, explained, and separately authorized.
- Tests: Deterministic mocked ORSR unit/integration tests plus final real local ORSR/API/UI scenario using synthetic entity terms and sanitized evidence.
- Documentation/minimal example: Update ORSR/voice routing docs and `examples/slovak_company_check_minimal_demo.py` or the default demo.
- Versioning: Bump changed API/core revisions.
- Readiness: Ready after T3; suggestion ranking threshold comes from T1.

## T5 — Design and implement a constrained local contract-search connector

### Prepared Technical Details

- Problem / idea source: No general local connector exists; backend OS commands would violate ADR-001 and the user-device boundary.
- Likely components: New connector package/service location To decide, signed capability manifest, local authorization/root selection, canonical path policy, connector/API contract, installer/update mechanism, tests, docs, and focused demo using synthetic files.
- Proposed approach: Create a separately authenticated least-privilege connector supporting only read-only filename/metadata search in canonical user-approved roots. Deny root/wildcard broadening, traversal, junction/symlink escape, hidden/system areas, archives, network/cloud locations unless separately approved. Return minimal relative metadata; opening, reading content, or upload are separate future capabilities.
- Security/compliance: Complete a threat model and connector deployment/authentication ADR first. Never execute transcript-generated commands. Never expose unrestricted absolute paths or contents in platform logs.
- Acceptance criteria:
  - [ ] Search cannot escape approved roots through traversal, junctions, symlinks, race conditions, case/Unicode tricks, or malformed patterns.
  - [ ] Scope grants are explicit, revocable, expiring, user/capability-bound, and visible.
  - [ ] Zero/multiple matches return minimal metadata without opening/uploading files.
  - [ ] Offline, untrusted, outdated, or policy-mismatched connectors fail closed.
- Tests: Cross-platform matrix limited to approved OSs; property/fuzz/security tests; synthetic filesystem integration; real local E2E with unique synthetic contract and final screenshot/manifest.
- Documentation/minimal example: Connector setup/security/rollback docs and a focused synthetic search demo; update `python examples/minimal_demo.py` only if the root package owns the connector interface.
- Readiness: `Not Ready Yet`; needs T1 decisions, connector ADR/threat model, OS scope, and T3.

## T6 — Implement mobile command preview, confirmation, and result UX

### Prepared Technical Details

- Problem / idea source: Mobile has STT, `IntentMapper`, `RuleEngine`, and `VoiceSessionOrchestrator`, but needs gateway-backed proposal/authorization semantics.
- Likely components: `mobile_app/lib/chat/intent_mapper.dart`, rule engine/orchestrator, API client/state/UI, localization, compliance controls, tests, README/voice docs, and `pubspec.yaml` build revision.
- Proposed approach: Preserve editable transcript; call proposal endpoint; render capability, destination, data, scope, risk, and side effects; require accessible confirmation/cancel; support stale-preview restart, progress/cancellation, sourced results, and non-executing suggestions. Do not keep authorization solely in spoken yes/no without visible equivalent and bound pending state.
- Acceptance criteria: Mobile satisfies UC-001 AC-01/02/06–14 for enabled capabilities, including duplicate-event idempotency and typed fallback.
- Tests: Flutter unit/widget/orchestrator tests, synthetic voice loopback, accessibility checks, and final real local mobile/browser-target E2E evidence as applicable.
- Documentation/minimal example: Update mobile voice docs and focused Dart voice demo.
- Versioning: Increase only mobile build/revision number.
- Readiness: Ready when T3 contract is stable; local-search UX waits for T5.

## T7 — Implement web and chat-simulator command preview, confirmation, and result UX

### Prepared Technical Details

- Problem / idea source: UC-001 requires cross-client behavior; web/chat simulator must not diverge from mobile authorization semantics.
- Likely components: Actual React frontend/chat simulator modules identified during task implementation, shared API contracts, localization, accessibility, tests, and frontend docs. No conda commands.
- Proposed approach: Mirror the reviewed transcript, proposal, explicit confirmation, cancellation, stale-preview, progress, result provenance, and suggestion behavior through the same API contract. Provide typed/offline/error states and do not emulate successful backend results.
- Channel parity: Web frontend and chat simulator in scope; API contract authoritative; mobile behavior equivalent except platform-specific microphone/local-connector affordances.
- Acceptance criteria: Web/chat simulator satisfy applicable UC-001 AC-01/02/06–14 and expose equivalent accessible visual information.
- Tests: Unit/component, browser regression, accessibility, and real local frontend→API→PostgreSQL→real model/tool path with final screenshot/manifest; no route-intercepted final acceptance.
- Documentation/minimal example: Update frontend/chat simulator docs and focused frontend example where established.
- Readiness: Ready when T3 contract is stable; local-search UX waits for T5.

## T8 — Final conformance, E2E, operations, and controlled rollout

### Prepared Technical Details

- Problem / idea source: User-facing voice/tool execution requires real local evidence and architecture/compliance conformance before rollout.
- Proposed approach: Review implementation against UC-001, ADD-001, ADR-001, and target C4. Run complete real local services/PostgreSQL/current migrations and default real model with deterministic synthetic audio, users, companies, files, and unique run identifiers. Validate security abuse cases, privacy-safe telemetry, accessibility, rollback flags, connector revocation, and operational runbooks.
- Acceptance criteria:
  - [ ] UC-001 AC-01–AC-15 pass or are explicitly pending with prerequisites.
  - [ ] Architecture conformance and focused security/privacy reviews have no unresolved release blockers.
  - [ ] Sanitized manifest records provider/model route, services, synthetic identifiers, expected/observed sources, policy/capability versions, audit IDs, and no secrets/PII/raw audio.
  - [ ] Stable final screenshots demonstrate transcript review, authorization, ORSR result, and approved-root local result; rollback is exercised.
- Tests/evidence: Follow `docs/E2E_TEST_EVIDENCE_RULE.md`; mocked tests are preliminary only.
- Documentation/minimal example: Finalize API/mobile/frontend/connector/runbook/security/privacy docs and verify all focused demos plus `python examples/minimal_demo.py`.
- Readiness: Ready only after T3–T7 and all T1 blockers are closed.

## Channel parity matrix

| Channel | In scope | Expected behavior | Contract/endpoint | Auth | Error/offline UX |
|---|---|---|---|---|---|
| Chat simulator | Yes | Reviewed transcript, proposal, confirmation, result/suggestions | Versioned API contract from T3 | Existing authenticated API pattern To verify | Typed fallback; visible unavailable/denied/stale states |
| API direct | Yes | Propose/authorize/execute structured requests; no transcript execution | Versioned endpoints/schema from T3 | Existing API identity plus bound authorization | Typed structured errors; deny closed |
| Mobile app | Yes | Existing STT plus accessible preview/confirmation/cancel/result | Same API contract | Existing signed-in user/session To verify | Typed fallback; local/device STT where honest; offline capability status |
| Web frontend | Yes | Browser STT where available plus equivalent visual workflow | Same API contract | Existing signed-in user/session To verify | Typed fallback; visible microphone/provider errors |

## Blocking questions before GitHub tasks can be marked Ready

1. Is the first release mobile + web + chat simulator, and is the local connector Windows-only initially?
2. Should initial contract search inspect filenames/metadata only (recommended), or document contents too?
3. Do you approve creating T1–T8 as separate GitHub issues now, with T1 and T5 explicitly `Not Ready Yet` and dependent tasks kept out of `Ready` until their prerequisites close?

Idea Task Status: Ready for prepare-task at architecture-plan level; individual implementation readiness is dependency-gated above.
