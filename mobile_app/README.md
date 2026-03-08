# AIJurisDictA - AI Juris Digital Agent (Flutter)

Flutter mobile client prepared for local testing of the AIJurisDictA (AI Juris Digital Agent) chat workflow.

## Features

- Chat-bot style conversation UI.
- Rebranded mobile layout with login card at the top and blue legal-themed background from the footer artwork.
- Add supporting documents using the device camera.
- Add questions/answers by speech using the microphone button next to the chat input.
- Message area is centered between login header and selectors.
- Initial localized Jurisdicta welcome message shown on app start.
- Language/country selector is shown below the message area (`SK` default, `EN`, `GE`, with `DE` accepted as alias for German).
  - `AI User Simulator` (default for local tests)
  - `Read User`
- Local mode selector appears only when API base URL points to local hosts (`localhost`, `127.0.0.1`, `10.0.2.2`, `0.0.0.0`).
- Select country/language before chatting (default: `Slovakia (SK)`).
- Download generated summary/document PDF files directly from the mobile app once a session exists.
- App version is shown in the bottom-left corner of the screen.
- On startup, app checks latest GitHub release and prompts for update when a newer version is available.
  - default source: `mmaideveloper/aijurisdictionagents` -> `releases/latest`
  - override with `--dart-define=AIJ_GITHUB_OWNER=... --dart-define=AIJ_GITHUB_REPO=...`
- Uses the real API chat endpoints with API key auth:
  - `POST /v1/chat/sessions`
  - `POST /v1/chat/sessions/{session_id}/reply`
  - `POST /v1/chat/sessions/{session_id}/stream` (AI User Simulator mode)
  - Header: `x-api-key: aijuris`
- Default local API base URL for Android emulator: `http://10.0.2.2:8080`.
- Uses refreshed branding assets from provided logo/footer/icons set.
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


### Speech input

Use the microphone icon in the chat composer to dictate a message. Tap again to stop recording, then send the recognized text as a normal chat message.

## Local API contract

The app creates a chat session:

```json
{
  "discussion_type": "advice",
  "country": "SK",
  "language": "SK"
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

PDF exports are downloaded through:

- `GET /v1/chat/sessions/{session_id}/export?format=pdf&kind=summary`
- `GET /v1/chat/sessions/{session_id}/export?format=pdf&kind=document`
Use the `Summary PDF` and `Document PDF` buttons above the message composer.
Buttons are enabled after AI stream emits `result`/`done` (PDF must be generated first).
In `AI User Simulator` mode, submitting the instruction starts discussion streaming (SSE)
the same way as the chat simulator by using `user_simulation_mode=AIUserSimulatorAgent`.

## Log output location

- Android/iOS/Desktop: app documents directory + `/logs/mobile_<timestamp>.log`
- Web: browser console (no local file write support)

## Troubleshooting build failures

If the app fails to compile with named-parameter errors around locale/session creation,
make sure you are on a revision where locale is passed through all chat session calls.
This repository version now wires locale selection into both:

- `sendMessage(...)`
- `startDiscussionStream(...)`

so Flutter builds no longer fail on missing `locale` parameters.

- aligned Material color usage with Flutter 3.24 analyzer expectations to avoid CI analysis failures

- pin `flutter_svg` to a Dart 3.5-compatible range (`^2.1.0`) to match Flutter 3.24.0 in CI and prevent pub solver failures

## Minimal runnable example

```bash
python examples/minimal_demo.py
```

## CI environment API base URL

GitHub Actions mobile builds now read repository/environment variable `API_BASE_URL`
and pass it to Flutter as `--dart-define=AIJ_API_BASE_URL=...` for APK/Web builds.

Set `API_BASE_URL` per GitHub Environment (for example dev/stage/prod) to target
that environment's API during build.

CI pins Flutter to `3.24.0` on the `stable` channel with dependency caching,
uses the Flutter action cache and a 3-attempt retry loop for `flutter pub get`
(clearing `.dart_tool` and local Pub hosted/git caches between retries) to reduce
transient dependency installation failures caused by stale/corrupted cache state.

- pin `camera` to `0.10.5+9` to avoid newer transitive Android plugin requirements that can break CI APK builds on default runners.

CI auto-generates missing Flutter `android/` and `web/` platform scaffolding with
`flutter create` before build steps, so APK/web builds work even when only
shared Flutter sources are committed.

## Snapshot

Reference UI snapshot prepared for review of the mobile chat layout.

Open `docs/chat_ui_snapshot.html` in a browser for the updated rebrand layout preview.
