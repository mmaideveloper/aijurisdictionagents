# ADD-001 implementation task plan

## Record

- Status: Prepared; dependency-gated
- Date: 2026-08-30
- Confirmed first release: authenticated assistant at `agent.jurisdigta.eu`
- Input: existing browser-native STT with an editable transcript
- Local search: browser-selected folder, current session only, filenames and metadata only
- Out of scope: mobile, chat simulator, persistent directory grants, document-content indexing, and arbitrary OS/code execution
- Sources: [`UC-001`](../use-cases/UC-001-speech-input-and-safe-command-execution.md), [`ADD-001`](ADD-001-governed-speech-command-routing.md), [`ADR-001`](../decisions/ADR-001-route-speech-commands-through-policy-enforced-capabilities.md), and target [C4 evidence](../diagrams/jurisdigta/jurisdigta-target-speech-command-evidence.md)

## GitHub implementation tasks

| Order | Issue | Project/status | Outcome | Dependencies |
|---|---|---|---|---|
| 1 | [#691](https://github.com/mmaideveloper/aijurisdictionagents/issues/691) | Backend/system Project 5 — Ready | Finalize web-command governance, browser scope, risk policy, compliance evidence, and ADR alignment | None |
| 2 | [#692](https://github.com/mmaideveloper/aijurisdictionagents/issues/692) | Backend/system Project 5 — Backlog | Add versioned policy metadata to the capability catalog | #691 |
| 3 | [#693](https://github.com/mmaideveloper/aijurisdictionagents/issues/693) | Backend/system Project 5 — Backlog | Implement proposal/authorization, idempotent execution, and redacted audit | #691, #692 |
| 4 | [#694](https://github.com/mmaideveloper/aijurisdictionagents/issues/694) | Backend/system Project 5 — Backlog | Route ORSR and related company suggestions through the gateway | #692, #693 |
| 5 | [#695](https://github.com/mmaideveloper/aijurisdictionagents/issues/695) | Frontend Project 6 — Backlog | Add safe spoken-command UX and session folder search to `agent.jurisdigta.eu` | #693; #694 for company flow |
| 6 | [#696](https://github.com/mmaideveloper/aijurisdictionagents/issues/696) | Backend/system Project 5 — Backlog | Complete real E2E, security, privacy, conformance, and rollout validation | #691–#695 |

Each issue contains implementation boundaries, GDPR/EU AI Act safeguards, acceptance criteria, tests, documentation, versioning where applicable, and readiness/dependency status. Every issue must use its own branch and worktree.

## Delivery gates

1. Complete #691 and reconcile UC-001/ADD-001/ADR-001/C4 before moving dependent work to Ready.
2. Complete #692 before #693 so authorization consumes policy-complete, versioned capability metadata.
3. Route ORSR through the gateway in #694 before exposing its command UI as accepted behavior.
4. In #695, search only within a folder selected by the user for the current browser session. Do not persist a directory handle, read file contents, upload files, or claim support when the browser API is unavailable.
5. Treat mocked tests as preliminary. #696 must use real local services, PostgreSQL, the configured real model where applicable, synthetic audio/files/entities, final screenshots, and a sanitized manifest under `docs/E2E_TEST_EVIDENCE_RULE.md`.

Idea Task Status: Ready for prepare-task.
Status: Ready for implementation only in the dependency order above.
