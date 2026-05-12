class GeneratedCaseDocumentReference {
  const GeneratedCaseDocumentReference({
    required this.caseId,
    required this.docId,
    required this.userId,
  });

  final String caseId;
  final String docId;
  final String? userId;
}

final RegExp _caseDocumentPathPattern = RegExp(
  r'/v1/cases/([^/\s?]+)/documents/([^/\s?]+)(?:\?([^\s]+))?',
);

GeneratedCaseDocumentReference? extractGeneratedCaseDocumentReference(
  String content,
) {
  final match = _caseDocumentPathPattern.firstMatch(content);
  if (match == null) {
    return null;
  }
  final caseId = match.group(1)?.trim() ?? '';
  final docId = match.group(2)?.trim() ?? '';
  if (caseId.isEmpty || docId.isEmpty) {
    return null;
  }
  final query = match.group(3);
  String? userId;
  if (query != null && query.trim().isNotEmpty) {
    try {
      userId = Uri.splitQueryString(query)['user_id']?.trim();
      if (userId != null && userId.isEmpty) {
        userId = null;
      }
    } catch (_) {
      userId = null;
    }
  }
  return GeneratedCaseDocumentReference(
    caseId: caseId,
    docId: docId,
    userId: userId,
  );
}

String stripInternalGeneratedDocumentNotice(String content) {
  if (!_caseDocumentPathPattern.hasMatch(content)) {
    return content;
  }
  return content
      .split('\n')
      .where((line) => !_caseDocumentPathPattern.hasMatch(line))
      .join('\n')
      .trim();
}
