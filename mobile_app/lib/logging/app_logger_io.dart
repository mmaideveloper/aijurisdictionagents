import 'dart:convert';
import 'dart:io';

import 'package:path_provider/path_provider.dart';

import 'app_logger_base.dart';

class FileAppLogger implements AppLogger {
  FileAppLogger._(this._file, {required bool debugModeEnabled})
      : _debugModeEnabled = debugModeEnabled;

  final File _file;
  bool _debugModeEnabled;
  Future<void> _writeQueue = Future<void>.value();

  @override
  String get logFilePath => _file.path;

  @override
  bool get debugModeEnabled => _debugModeEnabled;

  @override
  Future<void> setDebugModeEnabled(bool enabled) async {
    _debugModeEnabled = enabled;
    final marker =
        File('${_file.parent.path}${Platform.pathSeparator}$_debugModeFileName');
    if (enabled) {
      await marker.writeAsString('1', flush: true);
    } else if (await marker.exists()) {
      await marker.delete();
    }
    await _enqueueWrite(
      'INFO',
      'Debug mode changed',
      context: <String, Object?>{'enabled': enabled},
      force: true,
    );
  }

  @override
  Future<void> info(String message, [Map<String, Object?> context = const {}]) {
    return _enqueueWrite(
      'INFO',
      message,
      context: context,
    );
  }

  @override
  Future<void> error(
    String message,
    Object error,
    StackTrace stackTrace, [
    Map<String, Object?> context = const {},
  ]) {
    final mergedContext = <String, Object?>{
      ...context,
      'error': error.toString(),
      'stack_trace': stackTrace.toString(),
    };
    return _enqueueWrite(
      'ERROR',
      message,
      context: mergedContext,
      force: true,
    );
  }

  Future<void> _enqueueWrite(
    String level,
    String message, {
    Map<String, Object?> context = const {},
    bool force = false,
  }) {
    if (!_debugModeEnabled && !force) {
      return Future<void>.value();
    }
    final entry = <String, Object?>{
      'timestamp': DateTime.now().toIso8601String(),
      'level': level,
      'message': message,
      'context': context,
    };
    final line = '${jsonEncode(entry)}\n';
    _writeQueue = _writeQueue.then(
      (_) => _file.writeAsString(
        line,
        mode: FileMode.append,
        flush: true,
      ),
    );
    return _writeQueue;
  }
}

String _timestampForFileName(DateTime timestamp) {
  final year = timestamp.year.toString().padLeft(4, '0');
  final month = timestamp.month.toString().padLeft(2, '0');
  final day = timestamp.day.toString().padLeft(2, '0');
  final hour = timestamp.hour.toString().padLeft(2, '0');
  final minute = timestamp.minute.toString().padLeft(2, '0');
  final second = timestamp.second.toString().padLeft(2, '0');
  return '$year$month$day' '_$hour$minute$second';
}

const String _debugModeFileName = 'debug_mode_enabled.flag';

Future<AppLogger> createAppLogger() async {
  final baseDirectory = await getApplicationDocumentsDirectory();
  final logDirectory =
      Directory('${baseDirectory.path}${Platform.pathSeparator}logs');
  await logDirectory.create(recursive: true);
  final stamp = _timestampForFileName(DateTime.now());
  final file =
      File('${logDirectory.path}${Platform.pathSeparator}mobile_$stamp.log');
  await file.create(recursive: true);
  final debugModeFile =
      File('${logDirectory.path}${Platform.pathSeparator}$_debugModeFileName');
  final debugModeEnabled = await debugModeFile.exists();
  final logger =
      FileAppLogger._(file, debugModeEnabled: debugModeEnabled);
  await logger.info(
    'Logger initialized',
    {'log_file': file.path, 'debug_mode_enabled': debugModeEnabled},
  );
  return logger;
}
