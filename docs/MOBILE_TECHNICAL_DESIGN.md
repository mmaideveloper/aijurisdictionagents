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

- Local browser/desktop debugging uses host API at `http://127.0.0.1:8080`.
- Android emulator builds may still need the emulator host gateway unless an
  explicit `AIJ_API_BASE_URL=http://127.0.0.1:8080` tunnel/reverse mapping is
  configured for that device.
- Local backend should expose `/v1/chat/*` and accept `x-api-key`.
- App runtime config is set via Dart defines:
  - `AIJ_API_BASE_URL` (default `http://10.0.2.2:8080`)
  - `AIJ_API_KEY` (default `aijuris`)
- Flutter web local run targets `http://127.0.0.1:8080` and expects API CORS to
  allow local origin (for example `http://127.0.0.1:7357`).

## Logging design

- Non-web targets:
  - Create `logs/` under app documents directory.
  - Create one log file per app run using timestamp in file name.
  - Persist request/response/error entries as JSON lines.
- Web target:
  - Emit the same log entries to browser console because file write is unavailable.
- Stream failures are separated from network failures in user-facing mobile
  messages. If `/v1/chat/sessions/{session_id}/stream` is reachable but the
  backend/model response fails, the app reports an assistant response failure
  with the correlation ID instead of saying that the API cannot be reached.

## Build & deploy preparation

GitHub Actions workflow `.github/workflows/mobile_flutter_build.yml`:
- Trigger on changes in `mobile_app/**` and workflow file.
- Build Android APK artifact for download.
- Build web output artifact as deployable static package.
- Run `flutter analyze --no-fatal-infos`; keep analyzer warnings at zero because warnings fail the workflow.

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

## Slovak-first local model validation
- Recommended local STT model: `whisper-small-multilingual` (fallback `whisper-base-multilingual` for weaker devices).
- Recommended local TTS model: `piper-sk_SK-katarina-medium`.
- Runtime hints can be set through `AIJ_LOCAL_STT_MODEL` and `AIJ_LOCAL_TTS_MODEL`.
- Assistant TTS supports voice barge-in: starting speech input or receiving a
  non-empty STT transcript stops current assistant speech so the user can
  interrupt long spoken answers.
- Browser `no-speech` STT timeouts are treated as soft no-input events instead
  of hard recognition failures.
- Test locally with:
  - `cd mobile_app && flutter test test/speech_service_test.dart`
  - `cd mobile_app && flutter test test/speech_flow_test.dart`
  - run app and confirm speech logs include selected `speech_runtime_mode` and transcript review before send.

- Profile voice selector now guarantees at least one Slovak voice option (`Slovak local default`, locale `sk-SK`) even when OS voice inventory does not expose Slovak voices.

## Recurring AI Simulator Voice Loopback

The required scheduled regression for spoken AI Simulator communication uses a
deterministic loopback harness instead of real microphone/speaker hardware. This
keeps the recurring gate stable while still validating the mobile voice state
machine, TTS/STT text round trip, transcript similarity checks, truncation
detection, and privacy metadata for both `local-device` and `azure` runtime
labels.

Local runner:

```powershell
.\scripts\run_mobile_voice_loopback.ps1 -IncludeAzure
```

The runner verifies:

- local API health at `http://127.0.0.1:8080/health`;
- `llm.provider=azurefoundry`;
- `database.backend=postgres`;
- local Flutter web mobile app availability at `http://127.0.0.1:7357`;
- 10 deterministic question/answer pairs for a generated `simulacia <number>`
  case title.

Artifacts are written to `runs\voice-simulator-tests\`. They contain source
text, TTS text, STT transcript, similarity score, truncation/interruption flags,
runtime mode, timestamps, and `raw_audio_persisted=false`. They do not contain
raw audio. Azure Speech settings are checked explicitly by the runner; missing
settings are reported as skipped unless the run uses `-RequireAzure`.

For a local listenable smoke test of the real AI Simulator Agent stream, run:

```powershell
.\scripts\run_mobile_voice_loopback.ps1 -SkipStart -LiveDiscussion -SpeakLiveDiscussion
```

That mode calls the real local `/v1/chat/sessions/{id}/stream` API with
`AIUserSimulatorAgent`, writes `voice-live-discussion.json`, and speaks each
received simulator/system turn sequentially through Windows SAPI. It is a manual
smoke check, not the only scheduled reliability gate, because live LLM timing
and host audio differ between machines.
