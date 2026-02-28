# AI Jurisdiction Mobile (Flutter)

Flutter mobile client prepared for local testing of the AI Jurisdiction chat workflow.

## Features

- Chat-bot style conversation UI.
- Add supporting documents using the device camera.
- Switch responder mode:
  - `AI User Simulator` (default for local tests)
  - `Real Person`
- Sends chat payloads to a **local API** endpoint (`http://10.0.2.2:8000/chat` for Android emulator).

## Run locally

```bash
cd mobile_app
flutter pub get
flutter run
```

> For iOS simulator/local device, replace `10.0.2.2` with your host machine IP (or `127.0.0.1` where appropriate) in `lib/main.dart`.

## Local API contract

The app posts this payload to `/chat`:

```json
{
  "message": "What are my tenant rights?",
  "mode": "aiUserSimulator",
  "documentPath": "/path/to/captured/image.jpg"
}
```

Expected success response:

```json
{
  "response": "Assistant answer"
}
```

## Snapshot

Reference UI snapshot prepared for review of the mobile chat layout.

![Mobile chat UI snapshot](docs/chat_ui_snapshot.svg)
