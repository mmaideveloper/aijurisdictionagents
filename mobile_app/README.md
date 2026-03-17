# AIJurisDictA - AI Juris Digital Agent (Flutter)

Flutter mobile client prepared for local testing of the AIJurisDictA (AI Juris Digital Agent) chat workflow.

## Features

- Chat-bot style conversation UI.
- Rebranded mobile layout with login card at the top and blue legal-themed background from the footer artwork.
- Add supporting documents using the device camera.
- Add questions/answers by speech using the microphone button next to the chat input.
- A dedicated `Speech input` toggle button lets the user enable or disable speech-to-text without removing the microphone action from the composer.
- Jurisdicta now speaks assistant messages aloud through text-to-speech, including the welcome message, speech prompts, and backend replies.
- When speech output is used, Jurisdicta selects an installed TTS voice that matches the current user language/country setup (`SK`, `CS`, `DE`, `EN`) instead of using one fixed speaker voice.
- German voice selection now explicitly prefers `de-DE` voices first, then `de-AT`, then `de-CH`, so the default German speaker is less likely to drift to the wrong dialect when multiple German voices are installed.
- The top control area now also shows an assistant voice picker for the current language and a play button so different speaker persons can be tested directly in the app.
- The speech flow now personalizes Jurisdicta's welcome with the stored user name; if the profile has no name yet, the first speech interaction asks for it and saves it to the signed-in profile.
- The chat input is multiline by default with at least 3 visible lines; pressing `Enter` inserts a new line and messages are sent only with the send button.
- Message area is centered between login header and selectors.
- The top header now uses a single compact line with `AIJurisDigta`, the app version, and the current auth action (`Login` or `Sign up` on the auth screen, `Sign out` after login).
- Built-in authentication UI:
  - `Sign up`: phone number + email/password (required), first/last name (optional), persisted through the API
  - `Sign in`: phone number first; if phone exists, user is signed in automatically through the API
  - if phone is not found, sign in fallback is shown for email/password
  - after sign-in, `Account` page allows updating phone number, password, first name, last name
  - browser/local web remembers the last signed-in phone number and pre-fills the sign-in form
  - local runs also prefill `+421944400166` when no phone was remembered yet
  - device builds expose OS autofill hints for phone/email/password on sign-in and sign-up fields
- Initial localized Jurisdicta welcome message shown on app start.
- Selected app language now localizes chat labels, dialogs, action text, and tooltips for `SK`, `EN`, and `GE` (`DE` is accepted as a German alias).
- Language/country selector is shown in the top control area below the login header (`SK` default, `EN`, `GE`, with `DE` accepted as alias for German).
  - `Real Agent` is now the default for local tests
  - `AI User Simulator Agent` remains available as the alternate local mode
- Public/Azure API runs also start in `Real Agent` mode by default; the local responder switch is still shown only for local API hosts.
- Local mode selector appears only when API base URL points to local hosts (`localhost`, `127.0.0.1`, `10.0.2.2`, `0.0.0.0`).
- Select country/language before chatting (default: `Slovakia (SK)`).
- Decorative top-row feature icons were removed to make room for the language/country and local-mode controls.
- Mobile chat bubbles hide machine-oriented payloads such as raw JSON blocks and show only user-facing question/answer text.
- Assistant chat bubbles no longer show backend agent labels such as `LawyerSlovakia`; the UI shows the localized assistant label and strips any leading agent prefix from the message text.
- The `Account` action now sits next to the PDF download buttons instead of the top header.
- Download generated summary/document PDF files directly from the mobile app once a session exists.
- Selecting a case now loads the latest 5 persisted case messages, with a paging button to load 5 more older messages while keeping chronological order in the chat area.
- If the selected case already has stored attachments, the mobile app shows download buttons for those case documents above the PDF/export controls.
- App version is shown in the bottom-left corner of the screen.
- On startup, app checks latest GitHub release and prompts for update when a newer version is available.
  - default source: `mmaideveloper/aijurisdictionagents` -> `releases/latest`
  - override with `--dart-define=AIJ_GITHUB_OWNER=... --dart-define=AIJ_GITHUB_REPO=...`
- Uses the real API chat endpoints with API key auth:
  - `POST /v1/users/sign-up`
  - `POST /v1/users/sign-in`
  - `POST /v1/users/sign-in/phone`
  - `PATCH /v1/users/{user_id}`
  - `POST /v1/chat/sessions`
  - `POST /v1/chat/sessions/{session_id}/reply`
  - `POST /v1/chat/sessions/{session_id}/stream` (AI User Simulator mode)
  - Header: `x-api-key: aijuris`
- Default local API base URL for Android emulator: `http://10.0.2.2:8080`.
- Uses refreshed branding assets from provided logo/footer/icons set.
- Assistant machine payloads such as `CASE_UPDATE_JSON` are hidden from the chat UI; the app shows only the user-facing text.
- Local AI User Simulator defaults now allow up to 60 minutes for question timeout, discussion duration, and communication window.
- Communication/error logging:
  - non-web targets write JSON log entries to a timestamped file in a `logs` folder
  - file name pattern: `mobile_YYYYMMDD_HHMMSS.log`
  - web target logs to browser console (file system write is not available on web)
- Mobile app now creates one flow correlation ID and sends it in `x-correlation-id` on every API request, so backend logs can be filtered to reconstruct full user flow.
- Each request also carries a unique `x-request-id` for per-call diagnostics while keeping the same flow correlation context.
- If an API error occurs, the correlation ID is included in the error message and a top-header `ID` button appears so the user can copy the ID for support communication.

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

Android note:

- Release builds also need `android.permission.INTERNET` in `android/app/src/main/AndroidManifest.xml`.
- Without that permission, Android can surface host lookup failures such as `No address associated with host name` even when the API URL itself is valid.


### Speech input

Use the `Speech input` button in the top control area to enable speech-to-text. When it is on, use the microphone icon in the chat composer to dictate a message. Tap the microphone again to stop recording, then send the recognized text as a normal chat message.

When `Speech input` is turned off, the microphone action in the composer is disabled until you turn speech back on.

Use the assistant voice dropdown to switch between installed speaker persons for the selected user language. Use the play button next to the dropdown to test the current speaker before continuing the conversation.

If the signed-in profile already has a name, Jurisdicta uses it in the welcome message.
If the profile has no name yet, the first speech interaction asks for the name, stores it in the profile, and then the user can continue dictating the actual question.
Assistant responses are also spoken aloud. When the microphone starts listening, the app stops playback first so Jurisdicta's voice is not fed back into speech recognition.

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
- `GET /v1/cases/{case_id}/history?user_id=...&offset=0&limit=5`
- `GET /v1/cases/{case_id}/documents/{doc_id}?user_id=...`
Use the `Summary PDF` and `Document PDF` buttons above the message composer.
Buttons are enabled after AI stream emits `result`/`done` (PDF must be generated first).
In `Real Agent` mode, when the lawyer decides a formal document is needed, the agent first asks for confirmation and the PDF buttons stay disabled until the follow-up reply actually prepares the document.
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

GitHub Actions mobile builds now read GitHub Environment variable `API_BASE_URL`
and pass it to Flutter as `--dart-define=AIJ_API_BASE_URL=...` for APK/Web builds.

Set `API_BASE_URL` per GitHub Environment (for example dev/stage/prod) to target
that environment's API during build.

The workflow binds to GitHub Environment `dev` by default for push/pull_request builds,
and `workflow_dispatch` allows overriding the environment with the `github_environment`
input. If `API_BASE_URL` is missing, the workflow fails instead of falling back to a hardcoded URL.

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
