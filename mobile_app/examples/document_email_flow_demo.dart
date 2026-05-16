import 'dart:io';

import 'package:ai_jurisdiction_mobile/chat/document_email_flow.dart';

Future<void> main() async {
  final flow = DocumentEmailFlow(
    backend: _DemoBackend(),
    speak: (message) async => stdout.writeln('TTS: $message'),
    retryPolicy: const DocumentEmailRetryPolicy(
      maxAttempts: 2,
      initialDelay: Duration.zero,
    ),
    delay: (_) async {},
  );

  await flow.requestDocumentGeneration();
  final event = DocumentEmailFlow.backendEventFromPayload(
    <String, Object?>{
      'stage': 'document_package_ready',
      'message': 'Dokumenty sú pripravené.',
      'details': <String, Object?>{'status': 'ready'},
    },
  );
  if (event != null) {
    await flow.applyBackendEvent(event);
  }

  await flow.requestEmailConfirmation(recipient: 'lawyer@example.com');
  await flow.acceptSpokenConfirmation(
    transcript: 'áno',
    sessionId: 'demo-session',
  );

  stdout.writeln('Final state: ${flow.state.name}, email id: ${flow.emailId}');
}

class _DemoBackend implements DocumentEmailBackend {
  @override
  Future<DocumentEmailSendResult> sendDocumentsEmail({
    required String sessionId,
    required String recipient,
    required bool confirmed,
  }) async {
    if (!confirmed) {
      return DocumentEmailSendResult(
        accepted: false,
        recipient: recipient,
        message: 'Confirmation is required.',
      );
    }
    return DocumentEmailSendResult(
      accepted: true,
      recipient: recipient,
      emailId: 'demo-email-1',
      message: 'Generated documents were queued for email delivery.',
    );
  }
}
