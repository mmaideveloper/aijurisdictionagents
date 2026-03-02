import 'dart:convert';
import 'dart:io';

import 'package:path_provider/path_provider.dart';

import 'app_logger_base.dart';

class FileAppLogger implements AppLogger {
  FileAppLogger._(this._file);

  final File _file;
  Future<void> _writeQueue = Future<void>.value();

  @override
  String get logFilePath => _file.path;

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
    );
  }

  Future<void> _enqueueWrite(
    String level,
    String message, {
    Map<String, Object?> context = const {},
  }) {
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

Future<AppLogger> createAppLogger() async {
  final baseDirectory = await getApplicationDocumentsDirectory();
  final logDirectory =
      Directory('${baseDirectory.path}${Platform.pathSeparator}logs');
  await logDirectory.create(recursive: true);
  final stamp = _timestampForFileName(DateTime.now());
  final file =
      File('${logDirectory.path}${Platform.pathSeparator}mobile_$stamp.log');
  await file.create(recursive: true);
  final logger = FileAppLogger._(file);
  await logger.info('Logger initialized', {'log_file': file.path});
  return logger;
}
