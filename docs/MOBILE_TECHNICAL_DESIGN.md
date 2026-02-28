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
  - Document attachment banner
- `CameraCapturePage`
  - Camera preview
  - Capture action returning local image path

## Data flow

1. User captures a document image from camera.
2. User sends message.
3. App creates/reuses backend chat session via `POST /v1/chat/sessions`.
4. App sends user text to `POST /v1/chat/sessions/{session_id}/reply`.
5. Response text (`content`) is rendered into transcript.
6. If a local document is attached, its local path is appended to the outgoing message text.

## Local testing assumptions

- Android emulator uses host API at `10.0.2.2`.
- Local backend should expose `/v1/chat/*` and accept `x-api-key`.
- App runtime config is set via Dart defines:
  - `AIJ_API_BASE_URL` (default `http://10.0.2.2:8080`)
  - `AIJ_API_KEY` (default `aijuris`)

## Build & deploy preparation

GitHub Actions workflow `.github/workflows/mobile_flutter_build.yml`:
- Trigger on changes in `mobile_app/**` and workflow file.
- Build Android APK artifact for download.
- Build web output artifact as deployable static package.

This provides quick distribution for testers and a deployable web preview while native store deployment credentials are not configured.

## Review snapshot

A visual snapshot of the proposed chat interface is maintained at `mobile_app/docs/chat_ui_snapshot.svg` and the source layout at `mobile_app/docs/chat_ui_snapshot.html`.
