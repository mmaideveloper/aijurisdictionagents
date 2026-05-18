import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;

import 'rule_engine.dart';

enum DocumentEmailFlowState {
  requested,
  generating,
  ready,
  awaitingEmailConfirmation,
  sending,
  sent,
  failed,
}

enum DocumentEmailMobileEvent {
  documentEmailRequested,
  documentEmailGenerating,
  documentPackageReady,
  documentEmailAwaitingConfirmation,
  documentEmailSending,
  documentEmailSent,
  documentEmailFailed,
}

typedef DocumentEmailTtsSpeaker = Future<void> Function(String message);
typedef DocumentEmailDelay = Future<void> Function(Duration delay);

class DocumentEmailBackendEvent {
  const DocumentEmailBackendEvent({
    required this.event,
    required this.state,
    required this.message,
    this.details = const <String, Object?>{},
  });

  final DocumentEmailMobileEvent event;
  final DocumentEmailFlowState state;
  final String message;
  final Map<String, Object?> details;

  static DocumentEmailBackendEvent? fromBackendPayload(
    Map<String, Object?> payload,
  ) {
    final rawStage = (payload['stage'] ?? payload['event'] ?? payload['status'])
        ?.toString()
        .trim()
        .toLowerCase();
    if (rawStage == null || rawStage.isEmpty) {
      return null;
    }

    final details = _objectMap(payload['details']);
    final rawStatus = (details['status'] ?? payload['status'])
        ?.toString()
        .trim()
        .toLowerCase();
    final message = (payload['message'] ?? '').toString().trim();
    final normalized = _normalizeBackendStage(
      stage: rawStage,
      status: rawStatus,
    );
    if (normalized == null) {
      return null;
    }
    return DocumentEmailBackendEvent(
      event: normalized.event,
      state: normalized.state,
      message: message,
      details: details,
    );
  }
}

class DocumentEmailRetryPolicy {
  const DocumentEmailRetryPolicy({
    this.maxAttempts = 3,
    this.initialDelay = const Duration(milliseconds: 200),
    this.backoffMultiplier = 2,
  })  : assert(maxAttempts > 0),
        assert(backoffMultiplier >= 1);

  final int maxAttempts;
  final Duration initialDelay;
  final int backoffMultiplier;

  Duration delayForAttempt(int attempt) {
    var multiplier = 1;
    for (var i = 1; i < attempt; i += 1) {
      multiplier *= backoffMultiplier;
    }
    return initialDelay * multiplier;
  }
}

class DocumentEmailSendResult {
  const DocumentEmailSendResult({
    required this.accepted,
    required this.recipient,
    this.emailId,
    this.message = '',
    this.transientFailure = false,
  });

  final bool accepted;
  final String recipient;
  final String? emailId;
  final String message;
  final bool transientFailure;
}

class DocumentEmailSendException implements Exception {
  const DocumentEmailSendException(
    this.message, {
    this.transient = false,
  });

  final String message;
  final bool transient;

  @override
  String toString() => message;
}

abstract class DocumentEmailBackend {
  Future<DocumentEmailSendResult> sendDocumentsEmail({
    required String sessionId,
    required String recipient,
    required bool confirmed,
  });
}

class HttpSessionDocumentEmailBackend implements DocumentEmailBackend {
  HttpSessionDocumentEmailBackend({
    required this.baseUri,
    required this.apiKey,
    http.Client? httpClient,
  }) : _httpClient = httpClient ?? http.Client();

  final Uri baseUri;
  final String apiKey;
  final http.Client _httpClient;

  @override
  Future<DocumentEmailSendResult> sendDocumentsEmail({
    required String sessionId,
    required String recipient,
    required bool confirmed,
  }) async {
    final uri =
        baseUri.resolve('/v1/chat/sessions/$sessionId/documents/send-email');
    final response = await _httpClient.post(
      uri,
      headers: <String, String>{
        'Content-Type': 'application/json',
        'x-api-key': apiKey,
      },
      body: jsonEncode(<String, Object?>{
        'recipient': recipient,
        'confirmed': confirmed,
      }),
    );
    final body = _decodeJsonObject(response.body);
    final responseRecipient =
        (body['recipient'] ?? recipient).toString().trim().toLowerCase();
    if (response.statusCode >= 200 && response.statusCode < 300) {
      return DocumentEmailSendResult(
        accepted: body['needs_confirmation'] != true,
        recipient: responseRecipient,
        emailId: body['email_id']?.toString(),
        message: (body['message'] ?? '').toString(),
      );
    }
    final detail = (body['detail'] ?? response.body).toString();
    throw DocumentEmailSendException(
      detail.isEmpty ? 'Document email request failed.' : detail,
      transient: _isTransientStatusCode(response.statusCode),
    );
  }
}

class DocumentEmailFlowSnapshot {
  const DocumentEmailFlowSnapshot({
    required this.state,
    required this.recipient,
    required this.attempts,
    required this.message,
    required this.emailId,
  });

  final DocumentEmailFlowState state;
  final String? recipient;
  final int attempts;
  final String message;
  final String? emailId;
}

class DocumentEmailFlow {
  DocumentEmailFlow({
    required DocumentEmailBackend backend,
    required DocumentEmailTtsSpeaker speak,
    DocumentEmailRetryPolicy retryPolicy = const DocumentEmailRetryPolicy(),
    Duration confirmationTimeout = const Duration(seconds: 30),
    DateTime Function()? now,
    DocumentEmailDelay? delay,
  })  : _backend = backend,
        _speak = speak,
        _retryPolicy = retryPolicy,
        _confirmationTimeout = confirmationTimeout,
        _now = now ?? DateTime.now,
        _delay = delay ?? ((duration) => Future<void>.delayed(duration));

  final DocumentEmailBackend _backend;
  final DocumentEmailTtsSpeaker _speak;
  final DocumentEmailRetryPolicy _retryPolicy;
  final Duration _confirmationTimeout;
  final DateTime Function() _now;
  final DocumentEmailDelay _delay;

  DocumentEmailFlowState state = DocumentEmailFlowState.requested;
  String? recipient;
  String? emailId;
  String message = '';
  int attempts = 0;
  DateTime? _confirmationRequestedAt;

  DocumentEmailFlowSnapshot get snapshot => DocumentEmailFlowSnapshot(
        state: state,
        recipient: recipient,
        attempts: attempts,
        message: message,
        emailId: emailId,
      );

  Future<void> requestDocumentGeneration() async {
    await _transition(
      DocumentEmailFlowState.requested,
      'Požiadali ste o prípravu dokumentov na odoslanie e-mailom.',
    );
  }

  Future<void> applyBackendEvent(DocumentEmailBackendEvent event) async {
    final eventMessage = event.message.isEmpty
        ? _defaultMessageForState(event.state)
        : event.message;
    await _transition(event.state, eventMessage);
  }

  Future<void> requestEmailConfirmation({
    required String recipient,
  }) async {
    final normalizedRecipient = recipient.trim().toLowerCase();
    if (normalizedRecipient.isEmpty || !normalizedRecipient.contains('@')) {
      await _transition(
        DocumentEmailFlowState.failed,
        'E-mail nemôžem odoslať, pretože adresa príjemcu nie je platná.',
      );
      return;
    }
    this.recipient = normalizedRecipient;
    _confirmationRequestedAt = _now();
    await _transition(
      DocumentEmailFlowState.awaitingEmailConfirmation,
      'Dokumenty odošlem na adresu $normalizedRecipient. '
      'Ak súhlasíte, povedzte áno.',
    );
  }

  Future<void> acceptSpokenConfirmation({
    required String transcript,
    required String sessionId,
  }) async {
    if (state != DocumentEmailFlowState.awaitingEmailConfirmation) {
      return;
    }
    final choice = parseSpokenConfirmation(transcript);
    if (choice == SpokenConfirmationChoice.yes) {
      await sendConfirmed(sessionId: sessionId);
      return;
    }
    if (choice == SpokenConfirmationChoice.no) {
      await _transition(
        DocumentEmailFlowState.failed,
        'Odoslanie e-mailu bolo zrušené.',
      );
    }
  }

  Future<bool> checkConfirmationTimeout({DateTime? at}) async {
    if (state != DocumentEmailFlowState.awaitingEmailConfirmation) {
      return false;
    }
    final requestedAt = _confirmationRequestedAt;
    if (requestedAt == null) {
      return false;
    }
    final current = at ?? _now();
    if (current.difference(requestedAt) < _confirmationTimeout) {
      return false;
    }
    await _transition(
      DocumentEmailFlowState.failed,
      'Potvrdenie odoslania e-mailu vypršalo. Dokumenty neboli odoslané.',
    );
    return true;
  }

  Future<void> sendConfirmed({required String sessionId}) async {
    final resolvedRecipient = recipient;
    if (resolvedRecipient == null || resolvedRecipient.isEmpty) {
      await _transition(
        DocumentEmailFlowState.failed,
        'E-mail nemôžem odoslať, pretože chýba príjemca.',
      );
      return;
    }
    attempts = 0;
    await _transition(
      DocumentEmailFlowState.sending,
      'Odosielam dokumenty e-mailom.',
    );

    while (attempts < _retryPolicy.maxAttempts) {
      attempts += 1;
      try {
        final result = await _backend.sendDocumentsEmail(
          sessionId: sessionId,
          recipient: resolvedRecipient,
          confirmed: true,
        );
        if (result.accepted) {
          emailId = result.emailId;
          await _transition(
            DocumentEmailFlowState.sent,
            result.message.isEmpty
                ? 'Dokumenty boli odoslané e-mailom.'
                : result.message,
          );
          return;
        }
        if (!result.transientFailure) {
          await _transition(
            DocumentEmailFlowState.failed,
            result.message.isEmpty
                ? 'Backend e-mail neprijal na odoslanie.'
                : result.message,
          );
          return;
        }
      } on DocumentEmailSendException catch (error) {
        if (!error.transient || attempts >= _retryPolicy.maxAttempts) {
          await _transition(DocumentEmailFlowState.failed, error.message);
          return;
        }
      }

      if (attempts < _retryPolicy.maxAttempts) {
        await _delay(_retryPolicy.delayForAttempt(attempts));
      }
    }

    await _transition(
      DocumentEmailFlowState.failed,
      'Dočasná chyba odoslania e-mailu pretrváva.',
    );
  }

  Future<void> _transition(
    DocumentEmailFlowState nextState,
    String nextMessage,
  ) async {
    state = nextState;
    message = nextMessage;
    await _speak(nextMessage);
  }

  static DocumentEmailBackendEvent? backendEventFromPayload(
    Map<String, Object?> payload,
  ) =>
      DocumentEmailBackendEvent.fromBackendPayload(payload);
}

class _NormalizedBackendStage {
  const _NormalizedBackendStage({
    required this.event,
    required this.state,
  });

  final DocumentEmailMobileEvent event;
  final DocumentEmailFlowState state;
}

_NormalizedBackendStage? _normalizeBackendStage({
  required String stage,
  String? status,
}) {
  final raw = status == null || status.isEmpty ? stage : '$stage:$status';
  if (stage == 'document_package_ready' ||
      stage == 'document_ready' ||
      raw == 'document_status:ready') {
    return const _NormalizedBackendStage(
      event: DocumentEmailMobileEvent.documentPackageReady,
      state: DocumentEmailFlowState.ready,
    );
  }
  if (stage == 'document_requested' ||
      stage == 'document_generation_requested' ||
      stage == 'document_email_requested') {
    return const _NormalizedBackendStage(
      event: DocumentEmailMobileEvent.documentEmailRequested,
      state: DocumentEmailFlowState.requested,
    );
  }
  if (stage == 'document_generating' ||
      raw == 'document_status:generating' ||
      raw == 'document_status:processing') {
    return const _NormalizedBackendStage(
      event: DocumentEmailMobileEvent.documentEmailGenerating,
      state: DocumentEmailFlowState.generating,
    );
  }
  if (stage == 'document_email_awaiting_confirmation') {
    return const _NormalizedBackendStage(
      event: DocumentEmailMobileEvent.documentEmailAwaitingConfirmation,
      state: DocumentEmailFlowState.awaitingEmailConfirmation,
    );
  }
  if (stage == 'document_email_sending') {
    return const _NormalizedBackendStage(
      event: DocumentEmailMobileEvent.documentEmailSending,
      state: DocumentEmailFlowState.sending,
    );
  }
  if (stage == 'document_email_sent' || stage == 'document_email_queued') {
    return const _NormalizedBackendStage(
      event: DocumentEmailMobileEvent.documentEmailSent,
      state: DocumentEmailFlowState.sent,
    );
  }
  if (stage == 'document_email_failed') {
    return const _NormalizedBackendStage(
      event: DocumentEmailMobileEvent.documentEmailFailed,
      state: DocumentEmailFlowState.failed,
    );
  }
  return null;
}

Map<String, Object?> _objectMap(Object? value) {
  if (value is Map<String, Object?>) {
    return value;
  }
  if (value is Map) {
    return Map<String, Object?>.from(value.cast<String, Object?>());
  }
  return const <String, Object?>{};
}

Map<String, Object?> _decodeJsonObject(String value) {
  if (value.trim().isEmpty) {
    return const <String, Object?>{};
  }
  final decoded = jsonDecode(value);
  if (decoded is Map) {
    return Map<String, Object?>.from(decoded.cast<String, Object?>());
  }
  return const <String, Object?>{};
}

bool _isTransientStatusCode(int statusCode) =>
    statusCode == 408 ||
    statusCode == 425 ||
    statusCode == 429 ||
    statusCode >= 500;

String _defaultMessageForState(DocumentEmailFlowState state) {
  switch (state) {
    case DocumentEmailFlowState.requested:
      return 'Pripravujem požiadavku na dokumenty.';
    case DocumentEmailFlowState.generating:
      return 'Dokumenty sa generujú.';
    case DocumentEmailFlowState.ready:
      return 'Dokumenty sú pripravené.';
    case DocumentEmailFlowState.awaitingEmailConfirmation:
      return 'Čakám na potvrdenie odoslania e-mailu.';
    case DocumentEmailFlowState.sending:
      return 'Odosielam dokumenty e-mailom.';
    case DocumentEmailFlowState.sent:
      return 'Dokumenty boli odoslané e-mailom.';
    case DocumentEmailFlowState.failed:
      return 'Odoslanie dokumentov e-mailom zlyhalo.';
  }
}
