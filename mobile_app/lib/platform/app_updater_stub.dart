abstract class AppUpdater {
  bool get supportsInAppUpdate;

  Future<String> downloadReleaseAsset({
    required Uri downloadUri,
    required String fileName,
  });

  Future<bool> canInstallPackages();

  Future<void> openInstallPermissionSettings();

  Future<void> startInstall(String filePath);
}

class _StubAppUpdater implements AppUpdater {
  @override
  bool get supportsInAppUpdate => false;

  @override
  Future<bool> canInstallPackages() async => false;

  @override
  Future<String> downloadReleaseAsset({
    required Uri downloadUri,
    required String fileName,
  }) {
    throw UnsupportedError('In-app update is not supported on this platform.');
  }

  @override
  Future<void> openInstallPermissionSettings() {
    throw UnsupportedError('In-app update is not supported on this platform.');
  }

  @override
  Future<void> startInstall(String filePath) {
    throw UnsupportedError('In-app update is not supported on this platform.');
  }
}

AppUpdater createAppUpdater() => _StubAppUpdater();
