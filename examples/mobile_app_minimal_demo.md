# Minimal runnable example: Flutter mobile app

```bash
cd mobile_app
flutter pub get
flutter run --dart-define=AIJ_API_BASE_URL=http://10.0.2.2:8080 --dart-define=AIJ_API_KEY=aijuris
```

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
