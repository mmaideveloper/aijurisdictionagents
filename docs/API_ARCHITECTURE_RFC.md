# RFC: API runtime and streaming architecture for Task #7

## Status
Accepted (initial implementation baseline)

## Context
`aijurisdictionagents` is a Python-first codebase. Task #7 requires a production-ready API that supports:
- chat messages with optional uploads,
- incremental streaming responses,
- conversation history,
- stop/cancel semantics,
- authentication and API keys.

## Decision
- **Framework:** FastAPI (Python 3.11+) for API runtime.
- **Streaming transport (phase 1):** Server-Sent Events (SSE).
- **Optional extension (phase 2):** WebSocket for advanced bi-directional scenarios.
- **Service location:** `api/aijuristiction-api` as dedicated API project.

## Rationale
- FastAPI maximizes code reuse with existing Python agents/orchestration.
- SSE maps cleanly to ChatGPT-style output streaming and works through common HTTP infrastructure.
- A dedicated `api/` project keeps deployment, versioning, and CI concerns isolated.

## Module boundaries
- `app/auth`: login, bearer token, API key validation.
- `app/chat`: session and message lifecycle, stream projection.
- `app/documents`: file upload validation + ingestion handoff.
- `app/sessions`: persistent session state + stop/cancel transitions.
- `app/core`: config, middleware, errors, logging, dependency wiring.

## Data model baseline
- `User`
- `Session` (states: `active`, `completed`, `stopped`, `failed`)
- `Message`
- `Attachment`
- `GenerationJob`

## Milestones
1. Skeleton + shared error model + health/version.
2. Session/message persistence + history read API.
3. Upload + stream + stop endpoints.
4. Auth/API keys, orchestration integration, hardening.

## Consequences
### Positive
- Minimal rewrite risk.
- Faster delivery of backend API with typing/tests.
- Straightforward containerization for Azure Container Apps.

### Trade-offs
- SSE is server-to-client only; client-to-server remains normal HTTP.
- Horizontal scaling of long streams requires connection-aware tuning.
