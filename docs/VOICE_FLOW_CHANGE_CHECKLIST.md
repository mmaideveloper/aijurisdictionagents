# Voice Flow Change Checklist

Use this checklist for every PR that changes mobile voice input, speech-to-text,
assistant speech output, voice intent mapping, or voice-triggered legal actions.

## Collection

- [ ] List what is collected: raw audio, transcript, intent, structured slots,
  case id, user id, trace id, request id, language, and device/runtime metadata.
- [ ] Confirm raw audio upload is blocked unless `consentGiven=true`.
- [ ] Confirm raw audio is not persisted unless `storeAudioEnabled=true` and a
  retention period is documented.
- [ ] Confirm transcript logging stores only necessary metadata, not full PII
  content.

## Transfer

- [ ] List every destination: device STT, Azure Speech STT/TTS, API endpoint,
  tool invocation, backend case storage, or local debug log.
- [ ] Confirm `redactSensitiveEntitiesBeforeSend=true` remains the default for
  voice metadata.
- [ ] Confirm full transcripts are not duplicated in tool metadata when
  structured slots are enough.
- [ ] Confirm logs include `trace_id`, `request_id` where available, and
  processing purpose.

## Deletion / Retention

- [ ] Describe how transient raw audio is discarded after recognition.
- [ ] If deterministic voice loopback artifacts are produced, confirm they are
  stored under `runs/voice-simulator-tests/`, contain no raw audio, and have a
  documented cleanup/retention expectation.
- [ ] Describe how case deletion removes voice-derived messages/documents through
  backend deletion controls.
- [ ] Confirm any new persisted voice artifact has a documented retention period
  and user deletion path.

## Transparency / Oversight

- [ ] Confirm UI or docs explain voice processing, raw audio behavior, transcript
  minimization, and legal-output review expectations.
- [ ] Confirm legal-risk actions still require human/user confirmation before
  execution.
- [ ] Confirm 5-second silence prompts preserve the draft on `no` and submit
  only on explicit `yes` or send command.
- [ ] Confirm the confirmation prompt does not loop while awaiting `yes/no`.
- [ ] Confirm microphone click during listening/confirmation disables speech
  input and prevents auto-restart until explicitly enabled again.
- [ ] Confirm assistant TTS is not interrupted by automatic STT fragments,
  breathing, or room noise.
- [ ] Confirm clicking the composer microphone during assistant TTS stops
  playback and starts user dictation.
- [ ] Confirm failure states do not silently switch to less compliant behavior.
- [ ] Run or update the deterministic AI Simulator voice loopback regression for
  10 question/answer pairs in both `local-device` and `azure` runtime labels,
  or document why the change is outside STT/TTS scope.
