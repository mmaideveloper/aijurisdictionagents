# Minimal runnable example: Flutter mobile app

## Full app

```bash
cd mobile_app
flutter pub get
flutter run --dart-define=AIJ_API_BASE_URL=http://10.0.2.2:8080 --dart-define=AIJ_API_KEY=aijuris
```

After launch, use the microphone icon in the chat input row to dictate a question or answer and then press send.

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
