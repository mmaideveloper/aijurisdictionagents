abstract class FileOpener {
  Future<bool> open(String path);
}

class _StubFileOpener implements FileOpener {
  @override
  Future<bool> open(String path) async {
    throw UnsupportedError('Opening files is not supported on this platform.');
  }
}

FileOpener createFileOpener() => _StubFileOpener();
