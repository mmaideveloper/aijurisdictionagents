# Mobile Voice Compliance

This document defines the GDPR and EU AI Act baseline for the mobile voice
pipeline. Voice features process potentially sensitive legal facts, so every
change must preserve consent gating, data minimization, traceability, deletion
controls, user transparency, and human oversight.

## Lawful Basis / Consent

- Voice input may be processed only after the user has accepted the current
  data-processing notice during registration or an equivalent explicit consent
  flow.
- Raw microphone audio must not be uploaded to a remote speech-to-text service
  unless `consentGiven=true`.
- `storeAudioEnabled=false` is the default. The mobile client uses transient
  audio buffers for recognition and does not persist raw audio locally.
- If consent is missing or revoked, local/device speech recognition may still be
  used when the platform does not upload raw audio through this app pipeline,
  but Azure Speech STT/raw audio upload must be disabled.
- Consent records must include the consent timestamp and notice version.

## Data Minimization for Audio / Transcript

- Collect only the audio segment needed for the active speech recognition turn.
- Do not log or persist full raw audio.
- Do not log full transcripts. Logs may include transcript length, language,
  action type, trace id, request id, and processing purpose.
- `redactSensitiveEntitiesBeforeSend=true` is the default for voice intent
  metadata. Raw transcript previews sent with tool metadata must redact common
  emails, long phone or identifier numbers, and explicit identifier labels.
- Structured slots may contain the minimum values needed to execute a user
  request, for example an email address for sending a document, but the full
  dictated transcript should not be duplicated when structured slots exist.

## Retention / Deletion Policy

- Raw audio is transient by default and should be discarded after speech
  recognition completes or fails.
- Mobile debug logs should contain operational metadata only and should not
  include full PII content.
- Deterministic local voice loopback artifacts may contain test transcripts for
  regression review, but not raw audio. Store those artifacts under
  `runs/voice-simulator-tests/` and delete them when they are no longer needed
  for local debugging or CI artifact review.
- Case messages and generated legal documents follow the case retention policy
  configured by the backend subscription and case lifecycle.
- Users must be able to delete a case from the mobile app; deleting a case must
  remove the case chat history, generated documents, and associated metadata
  according to backend deletion controls.
- If future audio storage is introduced, it must require
  `storeAudioEnabled=true`, a documented retention period, a user-visible
  purpose, and a deletion path before release.

## User Transparency Texts

Use short, direct UI text near the voice toggle or consent surface:

- "Voice input may process your spoken legal facts to create a transcript and
  answer your request."
- "Raw audio is not stored by default. In Azure Speech mode, audio is sent for
  speech recognition only after you have consented."
- "Transcripts may contain personal data. We minimize logs and redact sensitive
  entities from voice metadata."
- "AI legal outputs can contain mistakes. Review important legal-risk results
  with a qualified person before acting."
- "You can stop voice input at any time and delete cases from your account."

## Human Oversight for Legal-Risk Outputs

- Voice flows that create, update, send, or summarize legal documents must keep
  explicit user confirmation before executing the action.
- Profile changes and case-archive transitions require spoken confirmation.
- Legal-risk answers and generated documents must remain reviewable in text/PDF;
  the app must not make an irreversible legal filing or external submission
  solely from an unconfirmed voice transcript.
- Logs must retain traceability metadata (`trace_id`, `request_id`, processing
  purpose, action type) so a human reviewer can reconstruct the workflow without
  exposing full PII content.

## Recurring Voice Test Baseline

- The mandatory recurring AI Simulator voice regression uses deterministic
  STT/TTS loopback so no microphone hardware, speaker output, or raw audio
  storage is required.
- The test covers both `local-device` and `azure` runtime labels. Azure Speech
  settings must be reported explicitly when missing; the test must not silently
  claim Azure coverage from the local/device runtime.
- Test artifacts may include source text, TTS text, STT transcript, similarity
  score, truncation/interruption flags, and runtime metadata. They must mark
  `raw_audio_persisted=false`.
- Live microphone/speaker smoke testing is optional and must not become the only
  recurring gate because device and browser audio behavior is not deterministic.
- The optional listenable AI Simulator smoke test may speak real API stream
  messages sequentially through local OS TTS, but it must still persist only
  text/debug artifacts and must not record or store microphone audio.
