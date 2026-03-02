# AI Jurisdiction Mobile (Flutter)

Flutter mobile client prepared for local testing of the AI Jurisdiction chat workflow.

## Features

- Chat-bot style conversation UI.
- Add supporting documents using the device camera.
- Switch responder mode:
  - `AI User Simulator` (default for local tests)
  - `Real Person`
- Uses the real API chat endpoints with API key auth:
  - `POST /v1/chat/sessions`
  - `POST /v1/chat/sessions/{session_id}/reply`
  - `POST /v1/chat/sessions/{session_id}/stream` (AI User Simulator mode)
  - Header: `x-api-key: aijuris`
- Default local API base URL for Android emulator: `http://10.0.2.2:8080`.
- Includes AI Jurisdicta branded top logo and background graphic.
- Communication/error logging:
  - non-web targets write JSON log entries to a timestamped file in a `logs` folder
  - file name pattern: `mobile_YYYYMMDD_HHMMSS.log`
  - web target logs to browser console (file system write is not available on web)

## Run locally

```bash
cd mobile_app
flutter pub get
flutter run --dart-define=AIJ_API_BASE_URL=http://10.0.2.2:8080 --dart-define=AIJ_API_KEY=aijuris
```

For iOS simulator/local device, override `AIJ_API_BASE_URL` with your host IP, for example:

```bash
flutter run --dart-define=AIJ_API_BASE_URL=http://127.0.0.1:8080 --dart-define=AIJ_API_KEY=aijuris
```

## Local API contract

The app creates a chat session:

```json
{
  "discussion_type": "advice"
}
```

Then sends a message:

```json
{
  "content": "What are my tenant rights?"
}
```

Expected reply response includes:

```json
{
  "content": "Assistant answer"
}
```

If a camera document is attached, the app includes the local file path in the message text for context.

In `AI User Simulator` mode, submitting the instruction starts discussion streaming (SSE)
the same way as the chat simulator by using `user_simulation_mode=AIUserSimulatorAgent`.

## Log output location

- Android/iOS/Desktop: app documents directory + `/logs/mobile_<timestamp>.log`
- Web: browser console (no local file write support)

## Snapshot

Reference UI snapshot prepared for review of the mobile chat layout.

![Mobile chat UI snapshot](docs/chat_ui_snapshot.svg)
