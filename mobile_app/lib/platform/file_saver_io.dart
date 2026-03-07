import 'dart:io';
import 'dart:typed_data';

import 'package:path_provider/path_provider.dart';

abstract class FileSaver {
  Future<String?> save({
    required Uint8List bytes,
    required String fileName,
    required String contentType,
  });
}

class _IoFileSaver implements FileSaver {
  @override
  Future<String?> save({
    required Uint8List bytes,
    required String fileName,
    required String contentType,
  }) async {
    final baseDirectory = await getApplicationDocumentsDirectory();
    final downloadDirectory = Directory(
      '${baseDirectory.path}${Platform.pathSeparator}downloads',
    );
    await downloadDirectory.create(recursive: true);
    final safeName = _sanitizeFileName(fileName);
    final file = File(
      '${downloadDirectory.path}${Platform.pathSeparator}$safeName',
    );
    await file.writeAsBytes(bytes, flush: true);
    return file.path;
  }

  String _sanitizeFileName(String input) {
    final replaced =
        input.replaceAll(RegExp(r'[<>:"/\\|?*\u0000-\u001F]'), '_').trim();
    if (replaced.isEmpty) {
      return 'export.pdf';
    }
    return replaced;
  }
}

FileSaver createFileSaver() => _IoFileSaver();
