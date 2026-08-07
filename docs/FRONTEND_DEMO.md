# Frontend Demo App

Location: `frontend/aijurisdictionfronend`

The frontend is a React + TypeScript + Vite workspace for the JurisDigta client app.
It includes public pages, API-backed auth, protected app routes, case intake, and the
assistant workspace at `/app/assistant`.

## Quick start

Requires Node.js 18+.

```bash
cd frontend/aijurisdictionfronend
npm install
npm run dev
```

Open `http://localhost:5173`.

## Authentication layout

The sign-in and registration views share the card at `/auth`. On wide screens, the
card is centered and limited to `480px`; on narrower screens, it shrinks with the
page while the header and footer remain full-width.

## Minimal runnable example

From repo root:

```powershell
.\examples\frontend_demo.ps1
```

Default repo minimal runnable example:

```powershell
python examples/minimal_demo.py
```

## Assistant Gateway Flow

The protected assistant page lets a signed-in user:

- create a new case target or select an existing case ID
- send a legal question
- upload supporting documents
- receive an answer with case ID, status, document count, and next actions

The new-case intake form defaults the jurisdiction to `Slovensko` and the
opposing party to `ziadna`; users can edit both values before creating the case.

The browser does not call MCP tools directly. Production execution must go through:

```text
Browser -> Assistant Gateway -> auth/consent/policy -> case store + document ingestion -> MCP/tools -> answer
```

Default frontend endpoint:

```text
POST /api/assistant/cases/answer
```

Set `VITE_ASSISTANT_GATEWAY_URL` when the gateway is hosted elsewhere.

Multipart request fields:

- `question`: user question or case instruction.
- `case_mode`: `new` or `existing`.
- `case_id`: existing case ID, blank for new cases.
- `country`: currently `SK`.
- `language`: currently `sk`.
- `consents`: JSON object with `assistant_gateway`, `document_processing`, and `third_party_tools`.
- `documents`: zero or more uploaded files.

Expected JSON response:

```json
{
  "case_id": "CASE-...",
  "answer": "Assistant answer text",
  "status": "completed",
  "citations": ["documents/2026-06-20-contract.pdf"],
  "stored_documents": ["documents/2026-06-20-contract.pdf"],
  "next_actions": ["Upload missing invoice", "Confirm payment date"]
}
```

If the gateway is not reachable, the UI shows a deterministic local demo answer so
the question/upload/answer rendering path remains testable.

## Build

```bash
cd frontend/aijurisdictionfronend
npm run build
npm run preview
```
