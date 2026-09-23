# Streaming speech-to-text (#525)

The website and native mobile composer stream mono PCM16 audio to the authenticated
API while the microphone is active. Azure Speech continuous recognition returns
partial and final utterances. Stop finalizes the draft; only explicit Send submits
the edited text to chat. This flow never invokes TTS. #826 tracks optional website
playback, and #827 tracks Phase 2 browser-local STT evaluation.

## Operator setup

1. Install the API dependencies, including `azure-cognitiveservices-speech`.
2. Apply `databases/api/migrations/830_case_speech_overrides.sql` using the normal
   migration runner. Runtime databases remain under `runs/storage/api/`.
3. In AI model administration create an enabled `azure_speech` provider with its
   actual region, external=true and local=false. Review the approved processor,
   region, contractual retention and data-processing terms before enabling it.
4. Save exactly one enabled `api_key` credential through existing encrypted
   credential administration. Never embed it in web or mobile assets.
5. Create a profile and use **Configure streaming STT (SK/EN/DE)**. The bounded
   parameters are `{"capability":"speech_to_text","streaming":true,
   "locales":"sk-SK,en-US,de-DE"}`. Mark EU capability only after verifying the
   actual deployment. Token pricing is not speech pricing.
6. Add exact `speech_transcription` policies separately for `free` and paid plan
   codes. Select the external speech profile, allow external processing, require
   acknowledgement and EU routing where applicable. Disable implicit fallback.
   Speech fails closed on a positive token-based cost budget; duration-based
   billing/caps need a separately implemented policy before such budgets are used.
7. Disable the policy/profile to roll back to typed input. Generic `default` chat
   policies and global chat user overrides never serve as speech routes.

Existing profile/policy administration supplies configuration and audited changes.
An authenticated admin can choose a speech-only case override from the dictation
consent panel. It never changes the reasoning model. Only the implemented Azure
Speech adapter is eligible; registering another provider does not imply support.

## Contract and bounds

`GET /v1/speech/cases/{case_id}/route?user_id=...` requires the API key and valid
`x-jurisdigta-device-id` / `x-jurisdigta-device-token` headers. It discloses provider,
model, region, locale support and a revision binding consent to the route.
`PUT .../override` additionally requires an authenticated admin and case ownership.

`/v1/speech/stream` is a bidirectional WebSocket. Its first JSON frame contains
`type=start`, API key, user/device authentication, case ID, locale, explicit
`consent=true`, route revision and `format=pcm_s16le_16000_mono`. Credentials are
never query-string parameters. The first frame is limited to 8 KiB and ten seconds.
Browser Origin must be an allowed site or loopback development origin; native
clients without Origin still require full device authentication. Null Origin is
not supported. Configure explicit deployment origins through `CORS_ALLOW_ORIGINS`.

After `ready`, send binary PCM chunks, at most 16,000 bytes each. The browser
AudioWorklet resamples microphone audio into approximately 100 ms chunks; it does
not send independent WebM fragments. Maximum recording is 120 seconds / 3.84 MB.
Idle timeout is 15 seconds. One active session per user and 20 sessions per API
process are allowed. Deployments with multiple workers need a shared admission
limit at the gateway; these in-process limits must not be advertised as global.

Events: `partial` and `final` carry segment ID and text; clients replace partials
and deduplicate finals. `stop` closes audio input and allows up to 15 seconds for
provider finalization; `done` releases the draft for review. `cancel` discards the
unsent speech draft. Disconnect, navigation, lifecycle interruption, errors and
timeouts release capture/provider resources. Clients never reconnect/replay audio
or change providers automatically. Stale session results are ignored.

## Privacy and legal safeguards

Microphone permission and remote-processing consent are separate. Audio and unsent
transcripts stay in bounded transient buffers, not files, browser storage or audit
logs. Speech does not run through legal tools or chat agents. Logs contain route,
actor/case/session IDs, consent version, outcome, duration and byte counts only.
Provider-side retention is reviewed separately: no application persistence is not
a claim of zero provider retention. Only reviewed, explicitly sent text enters
normal case retention/deletion. Draft recognition is not a verified legal fact.

## Runnable examples and tests

Default repository example remains `python examples/minimal_demo.py`.
Run `python examples/streaming_stt_demo.py` for an isolated, credential-free STT
policy-resolution example; it does not claim to transcribe audio.

Focused deterministic protocol tests (not real E2E):

```powershell
.\conda\python.exe -m pytest api/aijuristiction-api/tests/test_speech_streaming.py
cd frontend/aijurisdictionfronend
npm run test -- src/__tests__/streamingSpeech.test.ts
```

Real local two-line Slovak speech acceptance:

```powershell
.\scripts\import_e2e_model_credentials_from_server.ps1 -VerifyModel
.\conda\python.exe scripts/prepare_speech_e2e.py --check
.\conda\python.exe scripts/prepare_speech_e2e.py
# In another terminal: start the migrated/seeded local API + MCP (real chat model).
.\conda\python.exe scripts/start_speech_e2e_services.py
# Start the local frontend with VITE_API_BASE_URL=http://127.0.0.1:8080.
# Then, in the test terminal:
.\conda\python.exe scripts/run_speech_e2e.py
```

The fixture preparer uses the existing ignored `AIJ_AZURE_SPEECH_KEY` and
`AIJ_AZURE_SPEECH_REGION` settings only server-side to seed encrypted credentials
and synthesize two Slovak utterances with silence between them. This synthesis is
a test-fixture operation, not product TTS. Never use a real person's recording.
It requires the approved `westeurope` resource and local task database. No secret
is printed. Existing model bootstrap handles only the approved chat credential.

The browser receives synthetic WAV audio through Chromium's microphone input.
It must show actual partial recognition before Stop and at least two rendered
text lines. It checks synthetic word error rate <=20%, the amount 100 EUR (spoken or numeric representation), no
automatic send/TTS, an explicit review edit and exact normalized text submission.
It retains recording/review/final screenshots and a sanitized route/timing/result
manifest. These initial synthetic checks are not a real-user accuracy claim or a
completed latency benchmark; release latency/accuracy budgets still require the
benchmark and owner agreement specified in #525.

Credentials travel to the browser harness through stdin only; traces and raw
request logs are deliberately disabled. Evidence and synthetic WAVs live under
ignored `artifacts/` and `runs/`. Delete them within seven days. The runner revokes
device tokens, disables the synthetic account and soft-deletes the case. Purge
the task database after review to remove remaining synthetic history/audits.

Missing credentials, fixtures, local services or real-route evidence means E2E is
pending/failed, never passed through a mock. Native-device acceptance and the
multi-run Slovak cold/warm latency benchmark must be recorded before release.

The API image uses Python 3.13 on Debian 12 (bookworm), with ALSA, OpenSSL 3
and CA certificates for the native Speech SDK. Require Speech SDK >=1.48.2.
See [Microsoft Speech SDK platform requirements](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/quickstarts/setup-platform).

## Implementation verification (2026-09-23)

API lint/type checks and the full API test suite pass (five existing skips).
Frontend: 166 tests pass; production build succeeds; lint has zero errors and
nine existing Fast Refresh warnings. Mobile: analysis clean and 129 existing
tests pass. These mobile regressions are not native microphone acceptance.
Core model-parameter/runtime-baseline tests and both minimal examples pass.

Real two-line Slovak E2E passed under the owner-approved non-EU synthetic-only
exception after securely importing the server runtime Speech settings. The final
run (`speech-525-8355fceba044`) displayed four live lines and 23 partial updates,
with zero normalized fixture word errors, exact reviewed-text submission and a
real Azure Foundry `gpt-4o-mini` chat route. First partial: 4,761 ms from consent
(includes initial fixture silence); Stop-to-final: 356 ms. These are individual
synthetic-run measurements, not production latency guarantees. The chat stream
reached its existing manual-reply pause; this validates submission/model routing,
not completion of a legal document.

Screenshots and sanitized manifests are under ignored `artifacts/speech-525-*`;
retain for no more than seven days. Production EU-resource acceptance, native
device lifecycle/permission acceptance, real cancellation/disconnect acceptance,
container certificate-trust resolution and multi-run performance budgets remain
release gates.

## Production warning: EU Speech resource required (#525)

The user approved a non-EU exception on 2026-09-23 for synthetic-audio testing
only. Use `--allow-non-eu-synthetic` with both speech E2E scripts and only the
isolated loopback E2E database. The exception does not approve production audio
processing or mark the resource as EU-capable.

**Before production deployment, warn the owner to create a new Azure Speech
service in the EU.** Configure its encrypted key/region, restore EU-required
speech policies, validate processor/retention settings, rerun real Slovak speech
acceptance against that EU service, and obtain the owner's release approval.
Do not copy the test exception policy or non-EU credential to production.

## Visible microphone state

The top-right microphone opens the consent flow and has a bordered selected state
through setup, recording and finalization. The adjacent status explicitly says
microphone off before consent and after Stop/Cancel, microphone on while recording,
and waiting/finalizing during transitions. Clicking the active microphone stops
recording; choosing Chat cancels and discards the unsent speech draft.

The recording composer shows a red status dot, `mm:ss` timer, Stop/Cancel and a
32-bar history of measured microphone RMS volume. Silence stays flat: bars are
not a simulated animation. Reduced-motion preferences disable pulsing/transitions.
The real browser E2E starts from the top-right icon, verifies its selected state,
checks nonzero audio activity and confirms microphone-off after finalization.
Run `python scripts/run_speech_e2e.py --allow-non-eu-synthetic` with the documented
local services/fixture for the currently approved synthetic-only exception.

Visual-state acceptance run `speech-525-73958b02ed47` passed with the real
synthetic Slovak fixture: selected top-right microphone border, explicit on/off
status, measured audio activity, four live transcript lines, 22 partial events,
editable review and exact submitted text. Finalization took 416 ms in this run.
Evidence is under `artifacts/speech-525-73958b02ed47/` (seven-day retention).

The real E2E also captures `start-consent.png`, `started-recording.png` and
`stopped-transcript.png`, showing the start/record/stop sequence before any
review edit or Send. These follow the same synthetic-only and retention rules.
