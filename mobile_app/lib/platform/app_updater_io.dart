import 'dart:io';

import 'package:flutter/services.dart';
import 'package:path_provider/path_provider.dart';

class AppDownloadProgress {
  const AppDownloadProgress({
    required this.receivedBytes,
    required this.totalBytes,
  });

  final int receivedBytes;
  final int totalBytes;

  double? get fractionComplete {
    if (totalBytes <= 0) {
      return null;
    }
    return receivedBytes / totalBytes;
  }
}

abstract class AppUpdater {
  bool get supportsInAppUpdate;

  Future<String> downloadReleaseAsset({
    required Uri downloadUri,
    required String fileName,
    void Function(AppDownloadProgress progress)? onProgress,
  });

  Future<bool> canInstallPackages();

  Future<void> openInstallPermissionSettings();

  Future<void> startInstall(String filePath);
}

class _IoAppUpdater implements AppUpdater {
  static const MethodChannel _channel =
      MethodChannel('ai_jurisdiction_mobile/app_updater');

  @override
  bool get supportsInAppUpdate => Platform.isAndroid;

  @override
  Future<bool> canInstallPackages() async {
    if (!supportsInAppUpdate) {
      return false;
    }
    return await _channel.invokeMethod<bool>('canRequestPackageInstalls') ??
        false;
  }

  @override
  Future<String> downloadReleaseAsset({
    required Uri downloadUri,
    required String fileName,
    void Function(AppDownloadProgress progress)? onProgress,
  }) async {
    if (!supportsInAppUpdate) {
      throw UnsupportedError('In-app update is not supported on this platform.');
    }

    final baseDirectory = await getTemporaryDirectory();
    final updatesDirectory = Directory(
      '${baseDirectory.path}${Platform.pathSeparator}updates',
    );
    await updatesDirectory.create(recursive: true);

    final file = File(
      '${updatesDirectory.path}${Platform.pathSeparator}${_sanitizeFileName(fileName)}',
    );

    final client = HttpClient();
    IOSink? sink;
    try {
      final request = await client.getUrl(downloadUri);
      request.headers.add(HttpHeaders.acceptHeader, 'application/octet-stream');
      final response = await request.close();
      if (response.statusCode < 200 || response.statusCode >= 300) {
        throw HttpException(
          'Failed to download update APK: ${response.statusCode}',
          uri: downloadUri,
        );
      }
      sink = file.openWrite();
      var receivedBytes = 0;
      final totalBytes = response.contentLength;
      await for (final chunk in response) {
        sink.add(chunk);
        receivedBytes += chunk.length;
        onProgress?.call(
          AppDownloadProgress(
            receivedBytes: receivedBytes,
            totalBytes: totalBytes,
          ),
        );
      }
      await sink.flush();
      return file.path;
    } finally {
      await sink?.close();
      client.close(force: true);
    }
  }

  @override
  Future<void> openInstallPermissionSettings() async {
    if (!supportsInAppUpdate) {
      throw UnsupportedError('In-app update is not supported on this platform.');
    }
    await _channel.invokeMethod<void>('openInstallPermissionSettings');
  }

  @override
  Future<void> startInstall(String filePath) async {
    if (!supportsInAppUpdate) {
      throw UnsupportedError('In-app update is not supported on this platform.');
    }
    await _channel.invokeMethod<void>('installApk', <String, String>{
      'filePath': filePath,
    });
  }

  String _sanitizeFileName(String input) {
    final replaced =
        input.replaceAll(RegExp(r'[<>:"/\\|?*\u0000-\u001F]'), '_').trim();
    if (replaced.isEmpty) {
      return 'app-update.apk';
    }
    return replaced;
  }
}

AppUpdater createAppUpdater() => _IoAppUpdater();
