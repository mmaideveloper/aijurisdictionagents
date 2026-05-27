# Minimal runnable example: Flutter mobile app

## Full app

```bash
cd mobile_app
flutter pub get
flutter run --dart-define=AIJ_API_BASE_URL=http://10.0.2.2:8080 --dart-define=AIJ_API_KEY=aijuris
```

Use `http://127.0.0.1:8080` for Flutter web/desktop runs on the development machine. `https://127.0.0.1:8080` will fail because the local API does not serve TLS. `http://10.0.2.2:8080` is only the Android emulator gateway to the host API.

After launch, use the microphone icon in the chat input row to dictate a question or answer and then press send. In Azure Speech mode, raw audio upload is blocked unless the signed-in account has accepted the current data-processing consent; local/device speech recognition does not persist raw audio through the app.

Recurring deterministic voice loopback test:

```powershell
.\scripts\run_mobile_voice_loopback.ps1 -IncludeAzure
```

This starts or verifies the local API, local PostgreSQL, and local Flutter web
mobile app, then runs a 10 question/answer AI Simulator Agent voice loopback
check. The mandatory path uses deterministic STT/TTS loopback, writes artifacts
under `runs\voice-simulator-tests\`, and does not persist raw audio.

If you want to test Android in-app upgrades from a GitHub Release APK, make sure
every published release build is signed with the same release keystore; otherwise
Android rejects the upgrade with a signature mismatch.

Optional local API smoke request:

```bash
SESSION_ID=$(curl -sS -X POST http://127.0.0.1:8080/v1/chat/sessions \
  -H 'Content-Type: application/json' \
  -H 'x-api-key: aijuris' \
  -d '{"discussion_type":"advice","country":"SK","language":"SK"}' | jq -r '.id')

curl -X POST "http://127.0.0.1:8080/v1/chat/sessions/${SESSION_ID}/reply" \
  -H 'Content-Type: application/json' \
  -H 'x-api-key: aijuris' \
  -d '{"content":"Hello"}'
```
