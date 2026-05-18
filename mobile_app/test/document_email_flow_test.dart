import 'package:ai_jurisdiction_mobile/chat/document_email_flow.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('DocumentEmailFlow', () {
    test('normalizes chat simulator document_package_ready event', () async {
      final spoken = <String>[];
      final flow = DocumentEmailFlow(
        backend: _FakeDocumentEmailBackend(),
        speak: (message) async => spoken.add(message),
      );

      final event = DocumentEmailFlow.backendEventFromPayload(
        <String, Object?>{
          'stage': 'document_package_ready',
          'message': 'Dokumenty su pripravene.',
          'details': <String, Object?>{
            'status': 'ready',
            'document_names': <String>['vypoved.pdf'],
          },
        },
      );

      expect(event, isNotNull);
      expect(event!.event, DocumentEmailMobileEvent.documentPackageReady);
      await flow.applyBackendEvent(event);

      expect(flow.state, DocumentEmailFlowState.ready);
      expect(spoken.single, 'Dokumenty su pripravene.');
    });

    test('times out while waiting for explicit email confirmation', () async {
      final spoken = <String>[];
      var now = DateTime.utc(2026, 5, 15, 10);
      final flow = DocumentEmailFlow(
        backend: _FakeDocumentEmailBackend(),
        speak: (message) async => spoken.add(message),
        confirmationTimeout: const Duration(seconds: 5),
        now: () => now,
      );

      await flow.requestEmailConfirmation(recipient: 'User@Example.com');
      now = now.add(const Duration(seconds: 6));
      final timedOut = await flow.checkConfirmationTimeout();

      expect(timedOut, isTrue);
      expect(flow.state, DocumentEmailFlowState.failed);
      expect(flow.recipient, 'user@example.com');
      expect(spoken.first, contains('user@example.com'));
      expect(spoken.last, contains('vypršalo'));
    });

    test('fails after backend temporary send errors exhaust retries', () async {
      final spoken = <String>[];
      final delays = <Duration>[];
      final backend = _FakeDocumentEmailBackend(
        failuresBeforeSuccess: 3,
        transientFailures: true,
      );
      final flow = DocumentEmailFlow(
        backend: backend,
        speak: (message) async => spoken.add(message),
        retryPolicy: const DocumentEmailRetryPolicy(
          maxAttempts: 3,
          initialDelay: Duration(milliseconds: 10),
        ),
        delay: (duration) async => delays.add(duration),
      );

      await flow.requestEmailConfirmation(recipient: 'lawyer@example.com');
      await flow.acceptSpokenConfirmation(
        transcript: 'áno',
        sessionId: 'session-123',
      );

      expect(flow.state, DocumentEmailFlowState.failed);
      expect(flow.attempts, 3);
      expect(backend.calls, 3);
      expect(delays, hasLength(2));
      expect(spoken, contains('Odosielam dokumenty e-mailom.'));
      expect(spoken.last, 'Temporary email service error');
    });

    test('sends after explicit yes and retries transient backend failure',
        () async {
      final spoken = <String>[];
      final backend = _FakeDocumentEmailBackend(
        failuresBeforeSuccess: 1,
        transientFailures: true,
      );
      final flow = DocumentEmailFlow(
        backend: backend,
        speak: (message) async => spoken.add(message),
        retryPolicy: const DocumentEmailRetryPolicy(
          maxAttempts: 3,
          initialDelay: Duration.zero,
        ),
        delay: (_) async {},
      );

      await flow.requestDocumentGeneration();
      await flow.applyBackendEvent(
        const DocumentEmailBackendEvent(
          event: DocumentEmailMobileEvent.documentEmailGenerating,
          state: DocumentEmailFlowState.generating,
          message: 'Dokumenty sa generujú.',
        ),
      );
      await flow.applyBackendEvent(
        const DocumentEmailBackendEvent(
          event: DocumentEmailMobileEvent.documentPackageReady,
          state: DocumentEmailFlowState.ready,
          message: 'Dokumenty sú pripravené.',
        ),
      );
      await flow.requestEmailConfirmation(recipient: 'lawyer@example.com');
      await flow.acceptSpokenConfirmation(
        transcript: 'ano',
        sessionId: 'session-123',
      );

      expect(flow.state, DocumentEmailFlowState.sent);
      expect(flow.emailId, 'email-2');
      expect(flow.attempts, 2);
      expect(backend.confirmedValues, <bool>[true, true]);
      expect(spoken, <String>[
        'Požiadali ste o prípravu dokumentov na odoslanie e-mailom.',
        'Dokumenty sa generujú.',
        'Dokumenty sú pripravené.',
        'Dokumenty odošlem na adresu lawyer@example.com. Ak súhlasíte, povedzte áno.',
        'Odosielam dokumenty e-mailom.',
        'Generated documents were queued for email delivery.',
      ]);
    });

    test('does not send when user rejects human oversight prompt', () async {
      final backend = _FakeDocumentEmailBackend();
      final flow = DocumentEmailFlow(
        backend: backend,
        speak: (_) async {},
      );

      await flow.requestEmailConfirmation(recipient: 'lawyer@example.com');
      await flow.acceptSpokenConfirmation(
        transcript: 'nie',
        sessionId: 'session-123',
      );

      expect(flow.state, DocumentEmailFlowState.failed);
      expect(backend.calls, 0);
    });
  });
}

class _FakeDocumentEmailBackend implements DocumentEmailBackend {
  _FakeDocumentEmailBackend({
    this.failuresBeforeSuccess = 0,
    this.transientFailures = false,
  });

  final int failuresBeforeSuccess;
  final bool transientFailures;
  final List<bool> confirmedValues = <bool>[];
  int calls = 0;

  @override
  Future<DocumentEmailSendResult> sendDocumentsEmail({
    required String sessionId,
    required String recipient,
    required bool confirmed,
  }) async {
    calls += 1;
    confirmedValues.add(confirmed);
    if (calls <= failuresBeforeSuccess) {
      throw DocumentEmailSendException(
        'Temporary email service error',
        transient: transientFailures,
      );
    }
    return DocumentEmailSendResult(
      accepted: true,
      recipient: recipient,
      emailId: 'email-$calls',
      message: 'Generated documents were queued for email delivery.',
    );
  }
}
