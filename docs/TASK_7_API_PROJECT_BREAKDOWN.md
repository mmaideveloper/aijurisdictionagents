# Task #7 — API Project Breakdown (Business + Technical Subtasks)

This document reviews GitHub issue **#7: "API project"** and rewrites it as a clear business task with an ordered technical implementation plan, including containerization and Azure deployment direction.

Source issue:
- https://github.com/mmaideveloper/aijurisdictionagents/issues/7

## 1) Business Task (refined)

Build and expose a production-ready API layer for `aijurisdictionagents` so the frontend can run a ChatGPT-style experience with streaming AI responses, file uploads, conversation history, and secure access.

### Business outcomes
- Users can start a legal-assistant conversation from the frontend and receive incremental streamed responses.
- Users can provide text instructions and supporting documents in one session.
- Users can fetch full conversation history and stop active generation.
- The system supports authentication (email/password) and API keys for protected API usage.
- The new API runtime is separated in a dedicated root folder: `api/`.
- The API can run consistently via Docker in local/dev/prod.
- The service has a clear cloud deployment path to Azure Container Apps.

### Non-functional business expectations
- Reliable error handling and observability (structured logs + traceable request/session IDs).
- Basic security controls (authentication, authorization, API key lifecycle, upload validation).
- API contracts that are frontend-friendly and documented.
- Containerized delivery (immutable image, environment-driven configuration).

## 2) Scope Clarification

### In scope
- New `api/` service project.
- REST endpoints + streaming endpoint(s).
- Conversation/session lifecycle and persistence of message state.
- Document upload and ingestion into current project pipeline.
- AuthN/AuthZ for users and API keys.
- Dockerfile + local compose setup for API dependencies.
- Azure Container Apps deployment blueprint.
- API documentation and minimal runnable demo.

### Out of scope (first increment)
- Billing/subscriptions.
- Multi-tenant enterprise role model.
- Fine-grained legal workflow customization UI.
- Full enterprise platform migration (e.g., complete polyglot service mesh).

## 3) Ordered Technical Subtasks (implementation order)

> Order is designed to reduce rework and unblock frontend integration early.

### Subtask 1 — API architecture decision + RFC
**Goal:** Decide API framework and transport strategy before coding.
- Compare options (FastAPI, Node/NestJS, other) against existing Python codebase reuse.
- Choose streaming protocol (SSE first; WebSocket optional extension).
- Define high-level module boundaries (`api/auth`, `api/chat`, `api/documents`, `api/sessions`).
- Output: architecture RFC in `docs/` + ADR entry.

**Acceptance criteria**
- Approved RFC with rationale and trade-offs.
- Chosen approach supports incremental token/message streaming.

---

### Subtask 2 — Bootstrap `api/` project skeleton
**Goal:** Create runnable API service with standards aligned to repo.
- Create root `api/` folder and project config.
- Add linting, typing, and test setup.
- Add health endpoint (`GET /health`) and version endpoint (`GET /version`).
- Add centralized error model and request ID middleware.

**Acceptance criteria**
- `api/` starts locally with one command.
- CI-style checks for lint/type/tests are runnable.

---

### Subtask 3 — Session + conversation domain model
**Goal:** Define and persist chat session lifecycle.
- Models: `User`, `Session`, `Message`, `Attachment`, `GenerationJob`.
- Store conversation messages with role metadata and timestamps.
- Session states: `active`, `completed`, `stopped`, `failed`.

**Acceptance criteria**
- Conversation can be created and message history persisted/retrieved.
- Data model supports attachment linkage and streaming partials.

---

### Subtask 4 — Endpoint: start/continue conversation with input + uploads
**Goal:** Implement issue requirement #1.
- `POST /v1/chat/messages` (text instruction + optional files).
- Multipart support and validation (size/type/count limits).
- Attach uploaded docs to active session.
- Trigger orchestration pipeline call.

**Acceptance criteria**
- Endpoint accepts text + files in one request.
- Invalid file inputs return consistent validation errors.

---

### Subtask 5 — Endpoint: stream AI response tokens/messages
**Goal:** Deliver ChatGPT-like incremental response streaming.
- `GET /v1/chat/stream/{session_id}` using SSE.
- Event types: `message.delta`, `message.completed`, `tool.status`, `error`, `done`.
- Support reconnect semantics (`Last-Event-ID` or cursor checkpoint).

**Acceptance criteria**
- Frontend receives partial response chunks in real time.
- Stream completes cleanly and final message is persisted.

---

### Subtask 6 — Endpoint: fetch full conversation history
**Goal:** Implement issue requirement #2.
- `GET /v1/chat/sessions/{session_id}/messages` with pagination.
- Include AI and user messages, attachments metadata, and generation status.

**Acceptance criteria**
- Frontend can fully rebuild chat transcript from endpoint output.

---

### Subtask 7 — Endpoint: stop active conversation/generation
**Goal:** Implement issue requirement #3.
- `POST /v1/chat/sessions/{session_id}/stop`.
- Cancel generation job and mark session state.
- Emit final stream event indicating termination reason.

**Acceptance criteria**
- Ongoing generation can be stopped deterministically.
- Stop action is idempotent and safe on already-finished sessions.

---

### Subtask 8 — Authentication + API key management
**Goal:** Implement issue requirement #4.
- `POST /v1/auth/login` (email/password; token issuance).
- API key model: create/revoke/list (hashed at rest).
- Auth middleware supporting bearer token and API key.

**Acceptance criteria**
- Protected endpoints reject unauthorized access.
- API key rotation/revocation works and is audited.

---

### Subtask 9 — Integrate existing agents/orchestration pipeline
**Goal:** Connect API layer to current `aijurisdictionagents` logic.
- Adapt orchestrator invocation to async API flow.
- Map pipeline outputs to stream events and persisted messages.
- Standardize domain-to-DTO transformations.

**Acceptance criteria**
- End-to-end flow reaches current agent orchestration with streaming output.

---

### Subtask 10 — Dockerize API service
**Goal:** Provide portable runtime for local/dev/prod.
- Add multi-stage `api/Dockerfile` optimized for size and startup time.
- Add `docker-compose` profile for API + storage dependency (if used).
- Include secure defaults (`non-root user`, `HEALTHCHECK`, env-based secrets).

**Acceptance criteria**
- API can be built and run with Docker locally.
- Same image can be promoted to cloud without rebuild.

---

### Subtask 11 — Azure Container Apps deployment blueprint
**Goal:** Define deployment standard for cloud hosting.
- Define required Azure resources: Container Apps, Container Registry, Log Analytics, managed identity, secrets.
- Define environment variables/secrets mapping for model providers and storage.
- Document ingress, autoscaling, and streaming behavior considerations for SSE.
- Provide CLI or IaC starter templates (Bicep/Terraform) for repeatable setup.

**Acceptance criteria**
- One documented path exists to deploy image from ACR to Azure Container Apps.
- Streaming endpoint behavior validated in Azure environment.

---

### Subtask 12 — Observability, reliability, and security hardening
**Goal:** Production baseline quality.
- Structured logging with correlation IDs.
- Metrics/tracing hooks for request latency and stream lifecycle.
- Upload scanning hook point, rate limit, payload size guards.
- Retry/circuit-breaker boundaries around external model calls.

**Acceptance criteria**
- Operational dashboards/log filters can trace one conversation end-to-end.

---

### Subtask 13 — API documentation + frontend integration contract
**Goal:** Make API consumable by frontend without ambiguity.
- OpenAPI spec with examples.
- Streaming event contract documentation.
- Error code catalog and auth flow documentation.

**Acceptance criteria**
- Frontend team can integrate without backend clarifications for happy path.

---

### Subtask 14 — Test strategy + minimal runnable examples
**Goal:** Validate all critical behavior.
- Unit tests for validators/services.
- Integration tests for all required endpoints.
- Stream contract tests (chunk ordering, end events, interruption).
- Minimal runnable demo script for local API smoke execution.

**Acceptance criteria**
- Automated tests cover required issue behavior and core failure modes.

## 4) Deployment Approach Decision: .NET Aspire vs better alternatives

### Short answer
For this repository, **.NET Aspire should not be the default primary path** for Task #7.

### Why
- Current backend domain logic is already in **Python** (`aijurisdictionagents`), so a Python-native API (FastAPI) minimizes rewrite risk and integration complexity.
- .NET Aspire is strongest when the services are mostly .NET or when a team already standardizes on .NET distributed app tooling.
- Introducing Aspire for a Python-first codebase adds a second runtime/orchestration abstraction without solving the core API requirements faster.

### Better primary option for Task #7
- Build API in Python (FastAPI), containerize with Docker, deploy to Azure Container Apps.
- Use Azure-native ops stack (Log Analytics, Application Insights/OpenTelemetry, Managed Identity, Key Vault refs).

### When Aspire can still be useful
Use Aspire **optionally** as a platform shell only if:
- You will orchestrate multiple mixed services (e.g., frontend + Python API + Redis + worker) and the team wants a unified local orchestration experience.
- You accept maintaining both .NET app-host project and Python service project.

In that case Aspire should be an optional orchestration layer, not the implementation host of the Python API.

## 5) Suggested Project/Issue Update Content

If updating the GitHub project item/issue directly, use this concise structure:
1. Replace issue description with section **Business Task (refined)**.
2. Add ordered checklist from section **Ordered Technical Subtasks**.
3. Add explicit deliverables: Docker image + Azure Container Apps deployment blueprint.
4. Tag as backend/API and set status to **Ready** (or **In progress** once started).
5. Add delivery milestones:
   - M1: skeleton + auth + history endpoints
   - M2: streaming + stop + docs ingestion
   - M3: docker + Azure deployment + hardening + docs + tests

## 6) Definition of Done for Task #7

Task #7 is done when:
- `api/` service exists and is runnable.
- Required endpoints (#1-#4 from issue) are delivered.
- Streaming works for frontend chat UX.
- Auth + API key controls are in place.
- Docker image is produced and runnable locally.
- Azure Container Apps deployment path is documented and validated.
- Docs and tests are complete and passing.

## 7) Implementation update requested (current iteration)

- Create dedicated API project folder at root: `api/aijuristiction-api`.
- Add build and deployment automation workflow for this API service.
- Add E2E test recommendation and starter for Playwright API testing.

### Concrete deliverables for this update
1. `api/aijuristiction-api` scaffold with health/version endpoints.
2. Docker assets (`Dockerfile`, `.dockerignore`, `docker-compose.yml`).
3. GitHub Actions workflow for CI build and optional Azure Container Apps deploy.
4. Playwright API E2E starter setup under `api/aijuristiction-api/e2e-playwright`.
