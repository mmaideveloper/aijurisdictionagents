# ADR-0001: Choose FastAPI + SSE for Task #7 API

## Status
Accepted

## Date
2026-02-12

## Context
The API for Task #7 must integrate with a Python orchestration codebase and support streaming responses.

## Decision
Use **FastAPI** for the API service and **SSE** for first streaming implementation.

## Alternatives considered
1. Node/NestJS API + Python orchestration adapter.
2. .NET Aspire-centered implementation.
3. FastAPI + WebSocket-only streaming.

## Why this decision
- FastAPI aligns with existing Python runtime and tooling.
- SSE provides simple incremental response delivery over standard HTTP.
- Keeps architecture focused and avoids introducing additional runtime complexity.

## Follow-up actions
- Implement session/message domain model and persistence.
- Add `POST /v1/chat/messages` and `GET /v1/chat/sessions/{session_id}/messages`.
- Add SSE stream endpoint and stop endpoint in next milestones.
