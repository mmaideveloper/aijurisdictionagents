import 'dart:convert';

import 'package:flutter/foundation.dart';

import 'app_logger_base.dart';
import 'app_logger_sanitizer.dart';

class WebConsoleLogger implements AppLogger {
  @override
  String? get logFilePath => null;

  @override
  bool get debugModeEnabled => false;

  @override
  Future<void> setDebugModeEnabled(bool enabled) async {}

  @override
  Future<void> info(String message,
      [Map<String, Object?> context = const {}]) async {
    final entry = <String, Object?>{
      'timestamp': DateTime.now().toIso8601String(),
      'level': 'INFO',
      'message': message,
      'context': sanitizeLogContext(context),
    };
    debugPrint(jsonEncode(entry));
  }

  @override
  Future<void> error(
    String message,
    Object error,
    StackTrace stackTrace, [
    Map<String, Object?> context = const {},
  ]) async {
    final entry = <String, Object?>{
      'timestamp': DateTime.now().toIso8601String(),
      'level': 'ERROR',
      'message': message,
      'context': sanitizeLogContext(<String, Object?>{
        ...context,
        'error': error.toString(),
        'stack_trace': stackTrace.toString(),
      }),
    };
    debugPrint(jsonEncode(entry));
  }
}

Future<AppLogger> createAppLogger() async {
  final logger = WebConsoleLogger();
  await logger.info('Web logger initialized');
  return logger;
}
