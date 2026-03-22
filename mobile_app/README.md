# AIJurisDictA - AI Juris Digital Agent (Flutter)

Flutter mobile client prepared for local testing of the AIJurisDictA (AI Juris Digital Agent) chat workflow.

## Features

- Chat-bot style conversation UI.
- Rebranded mobile layout with login card at the top and blue legal-themed background from the footer artwork.
- Add supporting documents using the device camera.
- Add questions/answers by speech using the microphone button next to the chat input.
- Speech input is off by default and is toggled by a microphone icon button next to `Account`.
- Assistant voice output is also off by default after login; the user must enable it manually in `Account`.
- Turning on speech input with the microphone button also enables assistant voice output for that session, so spoken replies follow voice interaction automatically.
- When a spoken assistant reply finishes in voice mode, the app automatically reopens the microphone so the user can continue speaking hands-free.
- Normal dictated messages now keep listening through short 1-2 second pauses and stop only after about 5 seconds of silence. When the microphone session stops, the current dictated message is submitted automatically.
- The speech flow also understands spoken send commands such as `Send`, `please send`, `Posli`, `Prosim odosli spravu`, `Senden`, or `Nachricht senden`, and submits the current dictated message immediately.
- When the user says a spoken command like `please create a new case` while another case is active, the app now asks for confirmation before archiving the current case. After confirmation it creates and switches to the new case, and if no new case name was spoken yet it asks for the name first.
- The Slovak and German localizations were also cleaned up so user-facing system prompts and settings use proper localized text instead of ASCII-only fallbacks.
- Speech and text command rules now go through a dedicated `RuleEngine` component so future request rules can be added without growing `main.dart` command branching.
- Generated legal documents are no longer shown back into chat as plain text or JSON payloads; instead, the app asks the user whether they want to see the document as PDF and keeps the PDF export action available.
- If the user starts a discussion without any selected case, the app now creates a case automatically, generates a short title from the discussion text, selects that case, and then sends the original message to the backend.
- The automatic upgrade dialog now includes a session-only `Skip to new start` checkbox. When checked, the app stops version monitoring for the rest of the current app run and resumes only after the next launch.
- When the user turns speech input on, Jurisdicta first says `Hallo, <first name>, I am listening.` if the profile contains a first name, otherwise `Hallo, I am listening.`.
- Speech input can now create a new case from spoken commands in Slovak, English, or German, for example `Create a new case with name ...`, `Vytvor novy pripad s nazvom ...`, `Vytvor mi novy case s nazvom ...`, or `Erstelle einen neuen Fall mit Namen ...`.
- If the spoken create-case command does not include a case title, the app asks for the new case name and then creates/selects the case after the next spoken title.
- Jurisdicta now speaks assistant messages aloud through text-to-speech, including the welcome message, speech prompts, and backend replies.
- Assistant speech output is intentionally slowed down for clearer playback in both local-device TTS and Azure Speech TTS mode.
- When speech output is used, Jurisdicta selects an installed TTS voice that matches the current user language/country setup (`SK`, `CS`, `DE`, `EN`) instead of using one fixed speaker voice.
- For Slovak on Android, the app now prefers an exact `sk-SK` voice as the default whenever one is available on the device.
- For `SK`, `CS`, and `GE`/`DE`, the speaker now retries voice discovery on startup and falls back across close Central European voices instead of caching an empty voice list immediately.
- Current fallback order:
  - `SK`: `sk-SK` -> Slovak-labeled voices -> `cs-CZ`/Czech -> English
  - `CS`: `cs-CZ` -> Czech-labeled voices -> `sk-SK`/Slovak -> English
  - `GE`/`DE`: `de-DE` -> `de-AT` -> `de-CH` -> German-labeled voices -> English
- German voice selection now explicitly prefers `de-DE` voices first, then `de-AT`, then `de-CH`, so the default German speaker is less likely to drift to the wrong dialect when multiple German voices are installed.
- The `Account` page now also contains the language/country selector and an assistant voice picker with a play button, so the user can choose from voices available for the selected language.
- The `Account` page now also contains an assistant voice-output switch. Turning it on enables spoken assistant replies for the current session.
- The app does not support uploading a custom TTS voice asset directly. It can only use voices exposed by the installed platform TTS engine; on Android, install another Slovak-capable TTS engine/voice and then select it in `Account` if it appears in the voice list.
- Speech routing now goes through a provider-based speech factory/service layer with `AIJ_SPEECH_MODE=local|azure`. `local` is the default and applies the speech timing directly to the device runtime: higher TTS speed, 5-second silence detection for STT, and shorter resume delay after assistant playback.
- `azure` mode now supports both Azure Speech TTS and Azure Speech STT. The app can derive both service URLs from `AIJ_AZURE_SPEECH_REGION`, or you can pass explicit split endpoints with `AIJ_AZURE_SPEECH_TTS_ENDPOINT` and `AIJ_AZURE_SPEECH_STT_ENDPOINT`.
- The speech flow now personalizes Jurisdicta's welcome with the stored user name; if the profile has no name yet, the first speech interaction asks for it and saves it to the signed-in profile.
- When the user changes the stored first or last name, the chat now appends a fresh assistant message greeting the updated full name.
- The chat input is now single-line; pressing `Enter` sends the message immediately (same as the send button).
- Message area is centered between login header and selectors.
- The top header now uses a single compact line with `AIJurisDigta`, the app version, and the current auth action (`Login` or `Sign up` on the auth screen, `Sign out` after login).
- Built-in authentication UI:
  - Account profile now includes a `Debug mode` switch (Android) that controls file logging and a `Share logs` action that opens the Android share sheet for the current log file.
  - `Sign up`: phone number + email/password (required), first/last name (optional), persisted through the API
  - `Sign in`: phone number first; if phone exists, user is signed in automatically through the API
  - if phone is not found, sign in fallback is shown for email/password
  - after sign-in, `Account` page allows updating password, first name, and last name; on Android it also populates the phone number from the device and locks that field when the device number is available
  - browser/local web remembers the last signed-in phone number and pre-fills the sign-in form
  - local runs also prefill `+421944400166` when no phone was remembered yet
  - Android builds now read the device phone number first on the auth screen and use it for both sign-in and sign-up phone fields
  - when Android returns a device phone number, both auth phone fields are read-only and locked to that value
  - device builds expose OS autofill hints for phone/email/password on sign-in and sign-up fields
- Initial localized Jurisdicta welcome message shown on app start.
- Signed-in session cache is now scoped to the configured API base URL, so switching between local API and dev/public API does not reuse the wrong user account/profile state.
- Selected app language now localizes chat labels, dialogs, action text, and tooltips for `SK`, `EN`, and `GE` (`DE` is accepted as a German alias).
- Language/country selector is shown on the `Account` page (`SK` default, `EN`, `GE`, with `DE` accepted as alias for German).
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
- The mobile app now remembers the last selected case per signed-in user and API base URL, so reopening the app returns to the same existing case instead of always jumping back to the first item in the case list.
- The case edit dialog now also shows the current case documents. Tapping a listed document downloads it and opens it with the same file-view flow used from the main case screen.
- When an existing case is opened and the next chat session starts, the API now seeds that session with the case's stored message history so the model can continue from the prior conversation context.
- If the selected case already has stored attachments, the mobile app shows download buttons for those case documents above the PDF/export controls.
- After the user uploads case documents, the app now waits until those uploads reach a terminal processing state and then automatically sends a follow-up request asking the backend to summarize and analyze the uploaded material under the selected country law, including problems, risks, missing parts, and outdated clauses.
- After a backend reply or completed AI discussion, the chat screen now shows a compact case-validation card with the latest validation accuracy, validation summary, legal-data freshness timestamp, and current core model version returned by the API session result metadata.
- The chat input row sits above a dedicated footer line, and the app version is shown on the last line in the bottom-left corner of the screen.
- On startup, app blocks the auth flow until `GET /health` returns healthy.
  - failed health checks show the current API error on screen
  - if the API is reachable but its database is not, the app shows the DB health error returned by `/health`
  - startup retry uses exponential backoff: `2s`, `4s`, `8s`, `16s`, then stays capped at `16s`
- After startup, the app checks for updates through the API every 1 minute, but only when `GET /health` is healthy.
  - update metadata is read from `GET /version`
  - on Android, if the API advertises an APK download URL, the app downloads it and opens the Android installer after user confirmation
  - if Android blocks sideload installs for this app, the app opens the `Install unknown apps` settings page and resumes installation when the user returns
- Uses the real API chat endpoints with API key auth:
  - `POST /v1/users/sign-up`
  - `POST /v1/users/sign-in`
- `POST /v1/users/sign-in/phone`
- `PATCH /v1/users/{user_id}`
- `GET /health`
- `GET /version`
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
flutter run --dart-define=AIJ_API_BASE_URL=http://10.0.2.2:8080 --dart-define=AIJ_API_KEY=aijuris --dart-define=AIJ_SPEECH_MODE=local
```

For iOS simulator/local device, override `AIJ_API_BASE_URL` with your host IP, for example:

```bash
flutter run --dart-define=AIJ_API_BASE_URL=http://127.0.0.1:8080 --dart-define=AIJ_API_KEY=aijuris --dart-define=AIJ_SPEECH_MODE=local
```


To run full Azure Speech mode instead of the local mode, add Azure Speech credentials:

```bash
flutter run --dart-define=AIJ_API_BASE_URL=http://10.0.2.2:8080 --dart-define=AIJ_API_KEY=aijuris --dart-define=AIJ_SPEECH_MODE=azure --dart-define=AIJ_AZURE_SPEECH_KEY=<speech-key> --dart-define=AIJ_AZURE_SPEECH_TTS_ENDPOINT=https://eastus2.tts.speech.microsoft.com --dart-define=AIJ_AZURE_SPEECH_STT_ENDPOINT=https://eastus2.stt.speech.microsoft.com
```

You can also pass `AIJ_AZURE_SPEECH_REGION=<speech-region>` and let the app derive both Azure Speech endpoints automatically.

For backward compatibility, `AIJ_AZURE_SPEECH_ENDPOINT` is still accepted as the TTS endpoint only.

Android note:

- Release builds also need `android.permission.INTERNET` in `android/app/src/main/AndroidManifest.xml`.
- Speech recording requires `android.permission.RECORD_AUDIO`.
- Without that permission, Android can surface host lookup failures such as `No address associated with host name` even when the API URL itself is valid.
- Phone prefill now requests `READ_PHONE_NUMBERS` and `READ_PHONE_STATE` at runtime on Android.
- Android phone-number lookup is best-effort only. Many carriers, SIMs, emulators, and Android builds do not expose the device number, so the app falls back to editable phone fields when no device number is available.
- In-app Android updates require `android.permission.REQUEST_INSTALL_PACKAGES` and a `FileProvider` entry in the manifest so the downloaded APK can be handed to the Android package installer.


### Speech input

Use the `Speech input` button in the top control area to enable speech-to-text. When it is on, use the microphone icon in the chat composer to dictate a message. The app now keeps the session open through short pauses, then stops and submits after about 5 seconds of silence. Clicking the send button or clicking the microphone while it is already listening also stops the session and submits the current dictated message. In Azure mode, the app records microphone audio and sends it to Azure Speech STT when the recording stops.

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
- `GET /v1/chat/sessions/{session_id}/result`
- `GET /v1/cases/{case_id}/documents/{doc_id}?user_id=...`
Use the single `Documents` button above the message composer to download all user-requested export documents (summary + document PDF).
On Android, the app now immediately tries to open the saved file in an external PDF/document app after the download finishes.
Buttons are enabled after AI stream emits `result`/`done` (PDF must be generated first).
In `Real Agent` mode, when the lawyer decides a formal document is needed, the agent first asks for confirmation and the PDF buttons stay disabled until the follow-up reply actually prepares the document.
In `AI User Simulator` mode, submitting the instruction starts discussion streaming (SSE)
the same way as the chat simulator by using `user_simulation_mode=AIUserSimulatorAgent`.
The app also reads `GET /v1/chat/sessions/{session_id}/result` metadata to show validation accuracy and the latest known legal-data update timestamp for the selected country.


## Debug mode and log sharing (Android)

- Open `Account` from the chat screen.
- Enable `Debug mode` to write operational logs into a file under the app documents `logs/` folder.
- Tap `Share logs` to open the Android share sheet and send the active log file to another app/device.
- When debug mode is disabled, regular info logs are not persisted to file.

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

For a full repository checklist to create additional GitHub Environments such as
`test` and `prod`, see `docs/GITHUB_ENVIRONMENTS.md`.

The workflow binds to GitHub Environment `dev` by default for push/pull_request builds,
and `workflow_dispatch` allows overriding the environment with the `github_environment`
input. If `API_BASE_URL` is missing, the workflow fails instead of falling back to a hardcoded URL.

Manual mobile workflow runs now also expose a `release` switch:

- `release=false` (default): build APK/web artifacts only
- `release=true`: after the release APK is built, the workflow publishes or updates a GitHub Release tagged with the mobile app version from `pubspec.yaml` and uploads `app-release.apk` as a release asset

The GitHub Release tag is the exact mobile app version, for example `0.1.1+2`,
so the in-app update check and the downloadable APK stay aligned. The app now
resolves the actual latest GitHub release from the API-provided release URL, so
a new mobile release can be detected without redeploying the API.

To keep Android upgrades installable over an existing app, published release APKs
must be signed with the same keystore every time. Configure these GitHub secrets
in the target environment or repository before running `release=true` builds:

- `MOBILE_ANDROID_KEYSTORE_BASE64`: base64-encoded release keystore file
- `MOBILE_ANDROID_KEYSTORE_PASSWORD`: keystore password
- `MOBILE_ANDROID_KEY_ALIAS`: signing key alias inside the keystore
- `MOBILE_ANDROID_KEY_PASSWORD`: signing key password

When all four secrets are present, CI decodes the keystore into a temporary file
and signs `app-release.apk` with that stable release key. If any secret is
missing, CI falls back to the debug key, which is useful for ad hoc testing but
can still cause Android signature mismatch errors during upgrade if the currently
installed app was signed with a different key.

The workflow also strips accidental line breaks from those secrets before use and
validates that the keystore password and alias can be opened with `keytool`. If
the secrets are present but invalid, normal CI builds fall back to the debug key
with a warning, while manual `release=true` runs fail early with a clear signing
error so an invalid APK is not published.

Local helper scripts:

- Export the release keystore as base64 for `MOBILE_ANDROID_KEYSTORE_BASE64`:
  `pwsh ./mobile_app/tool/export_release_keystore_base64.ps1`
- Build a signed release APK locally with the generated keystore:
  `pwsh ./mobile_app/tool/build_release_signed.ps1 -KeystorePassword "<password>" -KeyAlias "release" -ApiBaseUrl "http://10.0.2.2:8080"`

Mobile app versioning rule:

- For normal mobile app changes, increment only the revision/build suffix in `pubspec.yaml`.
- Keep the semantic version unchanged unless a release explicitly requires it.
- Example: `0.1.4+7` -> `0.1.4+8`.

For Android automatic upgrade, the GitHub Release must include an `.apk` asset.
The workflow uses `app-release.apk`, which the app prefers automatically during the update flow. Releases without an APK are treated as non-mobile releases, so the in-app upgrade prompt is skipped for them.
If Android shows "App not installed" due to package/signature conflict, it means
the installed build was signed differently (for example debug vs release). The app
now warns about this case; uninstall the existing app and then install the new APK.
For production-like update testing, install only APKs produced from the same
configured release keystore; otherwise Android correctly rejects the upgrade.

CI pins Flutter to `3.41.2` on the `stable` channel with dependency caching,
uses the Flutter action cache and a 3-attempt retry loop for `flutter pub get`
(clearing `.dart_tool` and local Pub hosted/git caches between retries) to reduce
transient dependency installation failures caused by stale/corrupted cache state.

- pin `camera` to `0.10.5+9` to avoid newer transitive Android plugin requirements that can break CI APK builds on default runners.

CI auto-generates missing Flutter `android/` and `web/` platform scaffolding with
`flutter create` before build steps, so APK/web builds work even when only
shared Flutter sources are committed.

The CI analyze step also scans files under `tool/`, so helper/demo scripts in that
folder should stay analyzer-clean and avoid warning-level lints.

Speech service unit tests now initialize `TestWidgetsFlutterBinding` before constructing
`FlutterTts`-backed services, which keeps the CI `flutter test` step stable after speech
service factory coverage was added.

Speech flow expectations now assert the actual localized Slovak prompt with diacritics
(`Ahoj, Martin, počúvam vás.`), so the unit test matches the current UI copy used by
the app.

## Snapshot

Reference UI snapshot prepared for review of the mobile chat layout.

Open `docs/chat_ui_snapshot.html` in a browser for the updated rebrand layout preview.
