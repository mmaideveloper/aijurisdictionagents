# Minimal runnable example: Flutter mobile app

```bash
cd mobile_app
flutter pub get
flutter run
```

Optional local API smoke request:

```bash
curl -X POST http://127.0.0.1:8000/chat \
  -H 'Content-Type: application/json' \
  -d '{"message":"Hello","mode":"aiUserSimulator","documentPath":null}'
```
