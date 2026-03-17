abstract class AppLogger {
  String? get logFilePath;
  bool get debugModeEnabled;

  Future<void> setDebugModeEnabled(bool enabled);

  Future<void> info(String message, [Map<String, Object?> context = const {}]);

  Future<void> error(
    String message,
    Object error,
    StackTrace stackTrace, [
    Map<String, Object?> context = const {},
  ]);
}
