import 'app_logger_base.dart';

class NoopLogger implements AppLogger {
  @override
  String? get logFilePath => null;

  @override
  Future<void> error(
    String message,
    Object error,
    StackTrace stackTrace, [
    Map<String, Object?> context = const {},
  ]) async {}

  @override
  Future<void> info(String message,
      [Map<String, Object?> context = const {}]) async {}
}

Future<AppLogger> createAppLogger() async {
  return NoopLogger();
}
