import 'package:ai_jurisdiction_mobile/chat/generated_document_message.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('extracts generated case document reference from assistant notice', () {
    const message =
        'Dokument je pripraveny.\n\nTechnicke udaje som ulozil do dokumentu pripadu: /v1/cases/case-123/documents/doc-456?user_id=user-789';

    final reference = extractGeneratedCaseDocumentReference(message);

    expect(reference, isNotNull);
    expect(reference!.caseId, 'case-123');
    expect(reference.docId, 'doc-456');
    expect(reference.userId, 'user-789');
  });

  test('removes internal generated document notice from visible chat content',
      () {
    const message =
        'Dokument je pripraveny na stiahnutie.\n\nTechnicke udaje som ulozil do dokumentu pripadu: /v1/cases/case-123/documents/doc-456?user_id=user-789';

    final visible = stripInternalGeneratedDocumentNotice(message);

    expect(visible, 'Dokument je pripraveny na stiahnutie.');
    expect(visible, isNot(contains('/v1/cases/')));
    expect(visible, isNot(contains('Technicke udaje')));
  });
}
