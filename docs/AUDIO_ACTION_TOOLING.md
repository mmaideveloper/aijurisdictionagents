# Audio and Action Tooling Architecture

## Existing action agents/tools
- `AIAddressValidatorAgent`
- `AIWebSearchAgent`
- `AICarValidatorAgent`
- `AIPropertyValidatorAgent`
- `EntityScreeningAgent`
- `CompanySearchAgent`
- `PersonSearchAgent`
- `AIUserSimulatorAgent`
- `AIAgentsValidator`
- `ValidationReport`
- `ValidatorInputs`

## New recognizer flow
1. `AIAudioToolRecognizerAgent` handles speech/STT intents (create case, prepare documents, send documents).
2. If intent is an action-intent, it delegates to `AIActionToolRecognizerAgent`.
3. `AIActionToolRecognizerAgent` recognizes action intent and calls one existing action agent:
   - company -> `CompanySearchAgent`
   - car -> `AICarValidatorAgent`
   - address -> `AIAddressValidatorAgent`

## GDPR/EU AI Act safeguards
- Data minimization: recognizers only extract required parameters (ICO, VIN/SPZ, address fragment).
- Transparency: response includes which tool was selected.
- Human oversight: when parameters are missing, agent asks user instead of auto-guessing.
- Traceability: `ActionRecognition` returns structured fields suitable for audit logging.

## Recommended next updates
- Replace keyword routing with explicit country-intent registry (`country -> intents -> tool adapter`).
- Add consent-gated execution hooks for high-risk registry lookups.
- Add policy checks before email/document actions (recipient verification + retention policy labels).
- Expose same recognizer contracts through API endpoints for mobile/web parity.

## Browser-native STT fallback (Issue #225)
- Web workspace voice/video transcript composer now supports browser-native microphone capture via Web Speech API when available.
- Audio is processed by the browser recognition runtime and only transcript text is inserted into the draft for user review before sending.
- If unavailable or denied, typed transcript input remains available.


## Slovak-first STT model recommendation
- **Primary target language:** Slovak (`sk-SK`) for both mobile and web voice capture.
- **Mobile recommendation:** on-device Whisper-family runtime (`whisper.cpp` integration) with Slovak-capable multilingual checkpoints (`small` or `base` depending on latency/device profile).
- **Web recommendation:** browser-native STT with locale preference `sk-SK`; keep typed-input fallback and add WASM offline recognizer in later phase for unsupported browsers.
- **Privacy baseline:** no raw audio persistence by default; only user-reviewed transcript text is submitted.
