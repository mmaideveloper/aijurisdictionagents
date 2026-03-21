# Mobile Riverpod Refactor

This document describes the first Riverpod-oriented refactor for the Flutter mobile app.

## What changed

- Added `flutter_riverpod` to support provider-driven state and dependency wiring.
- Introduced shared providers in `mobile_app/lib/state/mobile_app_providers.dart`.
- Added a command parsing/execution layer in `mobile_app/lib/app/` for future text/speech actions.
- Added a minimal runnable demo at `mobile_app/tool/riverpod_command_demo.dart`.

## Why

The previous implementation kept app composition, locale definitions, command handling, and large feature state inside `mobile_app/lib/main.dart`. Riverpod now provides a path to move shared state and command orchestration out of that monolith incrementally.

## Sync and retest status

- This branch is already based on the latest locally available integration commit in this workspace: `8bf03db`.
- A separate `main` branch or Git remote is not configured in this container, so there was no newer upstream branch to merge or rebase from.
- Retesting still requires a local Flutter SDK because this container does not provide `flutter` or `dart` commands out of the box.

## Minimal runnable example

```bash
cd mobile_app
dart run tool/riverpod_command_demo.dart
```

## Recommended retest commands

```bash
cd mobile_app
flutter pub get
flutter analyze
flutter test
```

## Next steps

- Move account settings state into Riverpod controllers.
- Move chat session state into Riverpod notifiers.
- Route all text and speech commands through the shared command executor.
