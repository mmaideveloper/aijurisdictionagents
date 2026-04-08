import 'package:open_filex/open_filex.dart';

abstract class FileOpener {
  Future<bool> open(String path);
}

class _IoFileOpener implements FileOpener {
  @override
  Future<bool> open(String path) async {
    final result = await OpenFilex.open(path);
    return result.type == ResultType.done;
  }
}

FileOpener createFileOpener() => _IoFileOpener();
