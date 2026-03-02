import 'app_logger_base.dart';
import 'app_logger_stub.dart'
    if (dart.library.io) 'app_logger_io.dart'
    if (dart.library.html) 'app_logger_web.dart' as impl;
export 'app_logger_base.dart';

Future<AppLogger> createAppLogger() => impl.createAppLogger();
