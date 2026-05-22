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
- [ ] Describe how case deletion removes voice-derived messages/documents through
  backend deletion controls.
- [ ] Confirm any new persisted voice artifact has a documented retention period
  and user deletion path.

## Transparency / Oversight

- [ ] Confirm UI or docs explain voice processing, raw audio behavior, transcript
  minimization, and legal-output review expectations.
- [ ] Confirm legal-risk actions still require human/user confirmation before
  execution.
- [ ] Confirm 10-second silence prompts preserve the draft on `no` and submit
  only on explicit `yes` or send command.
- [ ] Confirm assistant TTS barge-in ignores likely self-transcripts before
  treating STT text as user input.
- [ ] Confirm failure states do not silently switch to less compliant behavior.
