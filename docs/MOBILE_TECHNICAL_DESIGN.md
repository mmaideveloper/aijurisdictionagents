# Mobile App Technical Design (Flutter)

## Goal

Provide a mobile-first chat assistant app that supports legal conversation flows, camera-based document ingestion, local API testing, and a CI pipeline that builds distributable mobile artifacts.

## Runtime & stack

- Flutter (Dart 3.3+)
- Packages: `camera`, `http`
- Local test API target:
  - `POST /v1/chat/sessions`
  - `POST /v1/chat/sessions/{session_id}/reply`
  - Header `x-api-key`

## UI architecture

- `ChatHomePage`
  - Chat transcript list
  - Input composer
  - Responder mode selector (`aiUserSimulator` default, `realPerson` optional)
    - `aiUserSimulator`: starts `/stream` with `AIUserSimulatorAgent`
    - `realPerson`: uses `/reply` for direct user-lawyer interaction
  - Document attachment banner
  - AI Jurisdicta logo + branded SVG background
- `CameraCapturePage`
  - Camera preview
  - Capture action returning local image path

## Data flow

1. User captures a document image from camera.
2. User sends message.
3. App creates/reuses backend chat session via `POST /v1/chat/sessions`.
4. `realPerson` mode: app sends user text to `POST /v1/chat/sessions/{session_id}/reply`.
5. `aiUserSimulator` mode: app starts discussion via `POST /v1/chat/sessions/{session_id}/stream`.
6. Streamed `message` events are rendered into transcript continuously.
7. If a local document is attached, its local path is appended to the outgoing message text.
8. Communication and errors are logged as JSON entries with timestamp and context.

## Local testing assumptions

- Android emulator uses host API at `10.0.2.2`.
- Local backend should expose `/v1/chat/*` and accept `x-api-key`.
- App runtime config is set via Dart defines:
  - `AIJ_API_BASE_URL` (default `http://10.0.2.2:8080`)
  - `AIJ_API_KEY` (default `aijuris`)
- Flutter web local run can target `http://127.0.0.1:8080` and expects API CORS to allow local origin (for example `http://localhost:7357`).

## Logging design

- Non-web targets:
  - Create `logs/` under app documents directory.
  - Create one log file per app run using timestamp in file name.
  - Persist request/response/error entries as JSON lines.
- Web target:
  - Emit the same log entries to browser console because file write is unavailable.

## Build & deploy preparation

GitHub Actions workflow `.github/workflows/mobile_flutter_build.yml`:
- Trigger on changes in `mobile_app/**` and workflow file.
- Build Android APK artifact for download.
- Build web output artifact as deployable static package.

This provides quick distribution for testers and a deployable web preview while native store deployment credentials are not configured.

## Review snapshot

A visual snapshot of the proposed chat interface is maintained at `mobile_app/docs/chat_ui_snapshot.svg` and the source layout at `mobile_app/docs/chat_ui_snapshot.html`.

## Case memory and mobile case management (latest)

- Added case lifecycle over API for mobile: list, create, rename, soft delete.
- Enforced max 5 active cases per user (`/v1/cases` create returns `409` after limit).
- Chat session creation now carries `user_id` and `case_id` so replies/stream messages can be persisted in DB case communications.
- Mobile app now requires selecting/creating a case before sending messages and shows case selector + create/rename/delete actions.
- Existing and future chat messages are persisted for case-linked sessions; document path attachments are persisted as text document records.

Minimal runnable example:

```bash
python examples/minimal_demo.py
```
