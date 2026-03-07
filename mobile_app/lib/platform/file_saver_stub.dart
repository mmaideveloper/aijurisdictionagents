import 'dart:typed_data';

abstract class FileSaver {
  Future<String?> save({
    required Uint8List bytes,
    required String fileName,
    required String contentType,
  });
}

class _StubFileSaver implements FileSaver {
  @override
  Future<String?> save({
    required Uint8List bytes,
    required String fileName,
    required String contentType,
  }) async {
    throw UnsupportedError('Saving files is not supported on this platform.');
  }
}

FileSaver createFileSaver() => _StubFileSaver();
