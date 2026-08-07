# Jurisdigta current architecture review

Reviewed on 2026-07-22 from repository code, infrastructure definitions, and architecture/compliance documentation.

## Summary

Jurisdigta is a modular legal-assistance platform with React and Flutter clients, a FastAPI API, reusable Python agent/orchestration code, asynchronous document/law/email workers, PostgreSQL/pgvector persistence, private Blob Storage, Azure OpenAI/Foundry inference, and centralized Azure telemetry. The split between interactive API traffic and scheduled background work is clear and supports independent scaling and failure isolation.

The strongest architectural qualities are explicit deployable boundaries, private document storage, managed identities for Azure resource access, API-key protection on material API surfaces, source-backed legal retrieval, and observable worker/API runtimes. The main risks are governance and lifecycle gaps rather than missing core runtime components.

## Material review findings

| Priority | Finding | Architectural impact | Recommended direction |
|---|---|---|---|
| High | Consent prompts exist, but a central versioned consent ledger and revocation enforcement are not documented as implemented. | Consent-gated external checks cannot be audited consistently across UI, API, tools, and time. | Add a consent-policy service/store and enforce it at every gated tool boundary. |
| High | Retention, deletion, restriction, and export are not enforced end-to-end across PostgreSQL, Blob Storage, generated files, and telemetry. | Personal/legal data can outlive its purpose or be incompletely handled in data-subject requests. | Define a data-class retention matrix and implement coordinated DSAR/retention jobs with deletion evidence. |
| High | Human review is recommended in content, but a formal gate for legally consequential outputs is not represented in runtime architecture. | Users may treat generated filings or hard recommendations as final without accountable oversight. | Introduce intent risk tiers and a review/approval state machine before finalization or filing. |
| Medium | AI provenance/transparency metadata is not consistently guaranteed at the API contract boundary. | Clients and audit exports may not reliably identify AI-generated content, model/provider, limitations, or review status. | Add mandatory response/document provenance metadata and schema tests. |
| Medium | API, document processor, and laws collector share platform persistence and telemetry dependencies. | Schema or data-contract changes can create cross-container deployment coupling. | Version shared schemas/contracts and require backward-compatible migrations plus worker compatibility tests. |
| Medium | The infrastructure baseline permits Azure-service access to PostgreSQL and documents password authentication. | The database trust boundary is broader than least-privilege private networking and identity-based authentication. | Evaluate private endpoints/VNet integration and Microsoft Entra authentication; document accepted residual risk meanwhile. |
| Medium | Long-lived SSE streams are served by an API configured with a small replica range. | Connection pressure and deployments may affect availability or stream continuity. | Define capacity/SLO tests, graceful draining, retry/resume semantics, and scaling signals for streaming. |

## GDPR and EU AI Act assessment

The repository demonstrates privacy/security foundations: Blob public access is disabled, HTTPS/TLS settings are present, sensitive checks include consent prompts, and operational telemetry supports traceability. These are not sufficient by themselves for complete compliance. The architecture should treat consent evidence, data minimization, retention/deletion, output provenance, risk classification, and human oversight as explicit runtime responsibilities with auditable state transitions.

No claim in the diagrams should be read as legal certification. Data classifications are aggregate architecture annotations; they do not contain user-level data or secrets.

## Diagram scope and use

- [System context source](jurisdigta-current-context.mmd) answers who uses Jurisdigta and which external systems it depends on.
- [Container source](jurisdigta-current-container.mmd) answers which deployable/runtime parts form the Azure-oriented system.
- The diagrams describe the repository-observed **current** state. Conditional infrastructure modules are included because they are implemented deployment options; actual production enablement remains to be verified from authorized runtime inventory.

## Minimal runnable example

Run the existing system smoke example from the repository root:

```powershell
python examples/minimal_demo.py
```

To render a diagram when Mermaid CLI is available:

```powershell
npx -y @mermaid-js/mermaid-cli -i architecture/diagrams/jurisdigta/jurisdigta-current-container.mmd -o architecture/diagrams/jurisdigta/jurisdigta-current-container.svg
```
