# Mobile voice conversation settings

The profile screen includes **Record chat with voice** to make STT/TTS testing closer to human speech conversation.

## Recommended behavior implemented

- Enables assistant TTS output together with microphone input from one explicit user setting.
- Uses a 30 minute listen window with a 45 second pause window so users can finish long sentences with natural thinking pauses.
- Allows user barge-in while the assistant is speaking: non-echo STT fragments stop the assistant speech and continue processing the user turn.
- Keeps privacy-by-design defaults: the app stores the boolean preference and voice telemetry context only; it does not store raw audio.
- Logs the active voice conversation settings with the existing voice compliance context for traceable debugging.

## GDPR and EU AI Act baseline

This setting is opt-in and transparent in the profile UI. It is designed for data minimization: audio is used transiently for STT/TTS, `storeAudioEnabled` remains false, and sensitive entity redaction remains enabled before sending voice text. Legal-risk assistant output still remains a user-facing decision-support conversation, so human oversight is required before relying on generated legal content.

## Minimal runnable example

```bash
dart run mobile_app/examples/voice_conversation_settings_demo.dart
```

The example prints the recommended persisted settings and confirms that raw audio retention is disabled by app policy.
