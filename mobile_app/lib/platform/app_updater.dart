export 'app_updater_stub.dart'
    if (dart.library.io) 'app_updater_io.dart'
    if (dart.library.html) 'app_updater_stub.dart';
