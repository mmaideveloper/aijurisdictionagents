# chat-simulator-app

Standalone test application for simulating chat flows against `aijuristiction-api` before frontend deployment.

## Run locally

```bash
cd api/chat-simulator-app
pip install -e ".[dev]"
uvicorn app.main:app --reload --port 8090
```

Open `http://localhost:8090/chat-simulator` and set **API base URL** to your API service.

For local development, the simulator now defaults to `http://127.0.0.1:8080` and automatically normalizes loopback hostnames (`localhost`, `127.0.0.1`, `::1`) to the same host as the simulator page. This avoids the common browser `Failed to fetch` problem when the simulator is opened on `127.0.0.1` but the API field still points to `localhost`.

For local PostgreSQL validation, run the API with a persisted case backend:

```bash
DB_OPTION=postgres DB_CLOUD=postgresql://postgres:postgres@127.0.0.1:5432/aijurisdiction STORAGE_OPTION=local DOCUMENT_PROCESSOR_OPTION=api LOCAL_LLM_IO_LOGGING=1 uvicorn app.main:app --reload --port 8080
```

The simulator now supports:
- creating chat sessions with country/language/discussion type
- loading prepared case instructions directly from `api/chat-simulator-app/testcases/` into the rendered internal simulator page and copying the selected case into the instruction box
- supporting both `CaseDescription` and the legacy typo `CaseDescripton` in prepared-case JSON-like files
- preloading prepared-case `Documents` attachments from `api/chat-simulator-app/testcases/` into the browser file picker so they are immediately ready for `Upload To Case`
- auto-uploading prepared-case `Documents` to a newly created case right after `Create Session`, so testcase attachments are persisted without an extra manual `Upload To Case` click
  - this auto-upload is intentionally skipped when you select an existing case from the dropdown
- showing a clear prepared-case dropdown state when no local prepared cases are available
- rendering the simulator page with no-cache headers and versioned static asset URLs so browser refresh picks up the latest internal UI changes immediately
- showing an initial localized Jurisdicta welcome message in the End User Chat View (`SK` default, `EN`, `GE`, with `DE` accepted as alias for German)
- submitting a case instruction and optionally uploading text documents
- provisioning a real API user + persisted case, uploading documents through `POST /v1/cases/{case_id}/documents`, and binding new chat sessions to that case
  - the user provisioning form includes first name, last name, and address so document-generation tests can verify profile-backed party data
- listing existing persisted cases for the active simulator user from a dedicated dropdown, selecting one, and continuing the conversation on that case with a fresh `Create Session`
- loading the selected case history from `GET /v1/cases/{case_id}/history` so you can review the existing conversation before continuing
- showing the selected case documents immediately after case selection, including document metadata/status from the API
- previewing selected existing case documents inline in the simulator (`PDF` iframe preview for PDFs, text preview for text-based files, open/download fallback for binary files)
- listing API document templates in the **Document Templates** panel and generating a preview PDF from each template through `GET /v1/document-templates/{template_key}/preview/pdf`
- deleting all persisted cases for the active simulator user with one button when the API reaches the active-case limit (`Maximum number of cases reached (5)`)
  - this action now runs through the internal simulator backend, so it does not depend on browser-side cross-origin delete requests
- inspecting persisted document debug data from the API, including stored vectors, chunk counts, and the exact prompt chunks selected for the current query
- starting `POST /v1/chat/sessions/{session_id}/stream` and viewing streamed events in real time
- showing intermediate processing/tool events in the live stream log, including company-verification steps such as ORSR lookup start/result and which drafting inputs are still missing
- rendering document-ready/status `processing` events directly in the End User Chat View while keeping lower-level backend progress in the dedicated processing status area instead of flooding the visible transcript
- showing a dedicated live processing status with elapsed seconds so Azure/ORSR waits look like active backend work instead of a frozen UI
- immediately rendering the `Case instruction` as the first end-user message when `Start Stream` is clicked, before assistant events continue the chat
- showing a dedicated **AI Agent Questions** log (question-only view extracted from assistant turns)
- using the new right-side **End User Chat View** panel that renders core messages as user-facing chat bubbles
- truncating chat bubbles longer than `256` characters with clickable `viac...` expansion so long technical/legal messages do not flood the panel by default
- selecting reply mode (`ReadUser` or `AIUserSimulatorAgent`) from the right-side bottom chat panel (`ReadUser` is default)
- setting communication minutes for AI user simulation responses (`30` by default)
- using `Max discussion (minutes)` with default `60`
- in `AIUserSimulatorAgent` mode, the simulator answers each AI agent question before conversation finish flow
- sending manual end-user answers from the bottom input box and getting immediate lawyer response via `POST /v1/chat/sessions/{session_id}/stream` (`ReadUser` mode)
  - `Send answer` is enabled whenever the simulator is in `ReadUser` mode and a session already exists
  - if the stream has not started yet for the current session, clicking `Send answer` automatically starts the stream first
  - after the assistant asks the first question, the same click flow sends the typed answer and clears the input box
  - if the assistant ends the turn with a confirmation/request sentence but without a literal `?`, manual replies still remain available
  - simulator now sends manual replies through `POST /v1/chat/sessions/{session_id}/stream` in `ReadUser` mode, so backend `processing` events are visible in real time
  - while waiting for backend response, the simulator shows a localized frontend `Thinking...` system bubble (`Premyslam...`, `Premyslim...`, `Ich denke nach...`, or `Thinking...`)
  - backend `processing` updates still feed the live status bar, but only document-ready/document-status milestones are mirrored into the visible chat transcript
  - as soon as the first real streamed event arrives, the temporary frontend thinking bubble is removed and replaced by actual backend progress/messages
  - both frontend and backend progress bubbles are mirrored into the live `Messages` JSON panel until the next persisted `Refresh Messages` sync
  - the reply panel now shows the exact reason when manual reply is not ready yet, instead of relying on silent browser form validation
  - after a completed stream, `Send answer` stays available for follow-up questions such as asking for the current document status in the same session
- auto-downloading PDF export when user requests PDF and later says thank you during a completed stream
- fetching result payload and downloading exports as JSON or PDF (summary + requested document as separate PDF files)
- grouping `Create Session` and `Clear Session` next to the persisted-case controls so the setup flow stays in one place
- requiring a persisted case before `Create Session`; the intended flow is now `Ensure User` -> `Create Case` -> optional `Upload To Case` -> `Create Session`

For persisted document review, the simulator supports this optional order when you want API-side stored documents and retrieval debug:
- `Ensure User`
- `Create Case`
- `Upload To Case`
- optional `Refresh Existing Cases` -> select an existing case from the dropdown
- `Create Session`
- `Start Stream`
- `Send answer`

If `Create Case` fails with `Maximum number of cases reached (5)`, use `Delete All Cases` for the active simulator user and create a fresh case again.

If you do not need persisted document retrieval, you can skip `Ensure User`, `Create Case`, and `Upload To Case` entirely and use inline temporary documents or no documents at all.

If the active case or uploaded documents change after a session was created, the simulator invalidates that session and requires a fresh `Create Session` before continuing. This prevents the common error where the first streamed turn sees stored case context but later manual turns no longer have access to the updated case state.

## Default simulator inputs

Default values are loaded from:

- `static/default-inputs.json`
- `testcases/*.txt` for the prepared-case dropdown data embedded into the simulator page at render time

Current defaults:
- `language`: `SK`
- `instruction`: `Priprav vzor o prenajme`
- `reply mode`: `ReadUser`
- `communication minutes`: `30`
- `max discussion`: `60`

## Endpoints

- `GET /health`
- `GET /chat-simulator`
- `GET /version`
- `GET /static/*` (simulator assets)

## Minimal runnable example

```bash
cd api/chat-simulator-app
uvicorn app.main:app --port 8090
```


Version check:

```bash
curl http://localhost:8090/version
```
