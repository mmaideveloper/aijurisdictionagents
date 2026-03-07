// ignore_for_file: avoid_web_libraries_in_flutter, deprecated_member_use

import 'dart:html' as html;
import 'dart:typed_data';

abstract class FileSaver {
  Future<String?> save({
    required Uint8List bytes,
    required String fileName,
    required String contentType,
  });
}

class _WebFileSaver implements FileSaver {
  @override
  Future<String?> save({
    required Uint8List bytes,
    required String fileName,
    required String contentType,
  }) async {
    final blob = html.Blob(<Object>[bytes], contentType);
    final href = html.Url.createObjectUrlFromBlob(blob);
    final anchor = html.AnchorElement(href: href)
      ..download = fileName
      ..style.display = 'none';
    html.document.body?.append(anchor);
    anchor.click();
    anchor.remove();
    html.Url.revokeObjectUrl(href);
    return null;
  }
}

FileSaver createFileSaver() => _WebFileSaver();
