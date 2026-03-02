abstract class AppLogger {
  String? get logFilePath;

  Future<void> info(String message, [Map<String, Object?> context = const {}]);

  Future<void> error(
    String message,
    Object error,
    StackTrace stackTrace, [
    Map<String, Object?> context = const {},
  ]);
}
