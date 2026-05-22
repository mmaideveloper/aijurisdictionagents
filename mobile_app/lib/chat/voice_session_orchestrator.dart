import 'dart:async';
import 'dart:collection';

import 'rule_engine.dart';

const String voiceSessionConfirmationPrompt =
    'Môžem už odpovedať na otázku? Povedzte áno alebo nie.';

enum VoiceSessionPhase {
  idle,
  listening,
  processing,
  awaitingConfirmation,
}

class QueuedVoiceSessionAction {
  const QueuedVoiceSessionAction({
    required this.action,
    required this.idempotencyKey,
    required this.originalTranscript,
  });

  final RuleEngineAction action;
  final String idempotencyKey;
  final String originalTranscript;
}

class VoiceSilenceThresholdEvent {
  const VoiceSilenceThresholdEvent({
    required this.prompt,
    required this.draftMessage,
    required this.repeatedPrompt,
  });

  final String prompt;
  final String draftMessage;
  final bool repeatedPrompt;
}

class VoiceTranscriptResult {
  const VoiceTranscriptResult({
    required this.accepted,
    required this.duplicate,
    required this.queuedAction,
    this.confirmation,
  });

  final bool accepted;
  final bool duplicate;
  final QueuedVoiceSessionAction? queuedAction;
  final SpokenConfirmationChoice? confirmation;
}

typedef VoiceSessionSilenceCallback = void Function(
  VoiceSilenceThresholdEvent event,
);

class VoiceSessionOrchestrator {
  VoiceSessionOrchestrator({
    RuleEngine ruleEngine = const RuleEngine(),
    this.silenceThreshold = const Duration(seconds: 10),
    this.confirmationPromptForLanguage,
    this.onSilenceThresholdReached,
    this.onStateChanged,
  }) : _ruleEngine = ruleEngine;

  final RuleEngine _ruleEngine;
  final Duration silenceThreshold;
  final String Function(String? languageCode)? confirmationPromptForLanguage;
  final VoiceSessionSilenceCallback? onSilenceThresholdReached;
  final VoidCallback? onStateChanged;

  final Queue<QueuedVoiceSessionAction> _actionQueue =
      Queue<QueuedVoiceSessionAction>();
  final Set<String> _processedIdempotencyKeys = <String>{};

  Timer? _silenceTimer;
  bool isListening = false;
  DateTime? lastUserSpeechAt;
  RuleEngineAction? pendingIntent;
  String? draftMessage;
  bool awaitingConfirmation = false;
  bool _continueDraftAfterNo = false;
  VoiceSessionPhase phase = VoiceSessionPhase.idle;

  int get queuedActionCount => _actionQueue.length;

  void startListening({DateTime? now}) {
    isListening = true;
    _setPhase(VoiceSessionPhase.listening);
    lastUserSpeechAt ??= now ?? DateTime.now();
    _scheduleSilenceTimer();
  }

  void stopListening() {
    isListening = false;
    _silenceTimer?.cancel();
    _silenceTimer = null;
    if (!awaitingConfirmation && phase == VoiceSessionPhase.listening) {
      _setPhase(VoiceSessionPhase.idle);
    }
  }

  void clearDraft() {
    _clearPendingIntent();
  }

  void dispose() {
    _silenceTimer?.cancel();
    _silenceTimer = null;
  }

  VoiceTranscriptResult acceptTranscript({
    required String transcript,
    required bool isFinal,
    required DateTime speechStartedAt,
    required RuleEngineContext context,
    required bool submitMessageWhenNoRuleMatches,
    DateTime? receivedAt,
  }) {
    final normalizedTranscript = _normalizeTranscript(transcript);
    if (normalizedTranscript.isEmpty) {
      return const VoiceTranscriptResult(
        accepted: false,
        duplicate: false,
        queuedAction: null,
      );
    }

    final now = receivedAt ?? DateTime.now();
    isListening = true;
    lastUserSpeechAt = now;

    if (awaitingConfirmation) {
      final confirmation = parseSpokenConfirmation(transcript);
      if (confirmation == SpokenConfirmationChoice.yes) {
        return _confirmPendingIntent(
          transcript: draftMessage ?? transcript,
          speechStartedAt: speechStartedAt,
        );
      }
      if (confirmation == SpokenConfirmationChoice.no) {
        _continuePendingDraft();
        return const VoiceTranscriptResult(
          accepted: true,
          duplicate: false,
          queuedAction: null,
          confirmation: SpokenConfirmationChoice.no,
        );
      }
      _scheduleSilenceTimer();
      return const VoiceTranscriptResult(
        accepted: true,
        duplicate: false,
        queuedAction: null,
      );
    }

    draftMessage = _resolveDraftTranscript(transcript.trim());
    _continueDraftAfterNo = false;
    _setPhase(VoiceSessionPhase.listening);
    _scheduleSilenceTimer();
    final shouldExecuteImmediately =
        isFinal || _hasExplicitExecutionTerminator(normalizedTranscript);
    if (!shouldExecuteImmediately) {
      return const VoiceTranscriptResult(
        accepted: true,
        duplicate: false,
        queuedAction: null,
      );
    }

    final action = _ruleEngine.evaluate(
      input: transcript,
      context: RuleEngineContext(
        awaitingProfileName: context.awaitingProfileName,
        awaitingProfileField: context.awaitingProfileField,
        awaitingProfilePatchConfirmation:
            context.awaitingProfilePatchConfirmation,
        awaitingCaseArchiveConfirmation:
            context.awaitingCaseArchiveConfirmation,
        awaitingCaseTitle: context.awaitingCaseTitle,
        submitMessageWhenNoRuleMatches: submitMessageWhenNoRuleMatches,
        pendingProfilePatch: context.pendingProfilePatch,
        currentDraft: context.currentDraft,
        lastDictatedDraft: context.lastDictatedDraft,
        correlationId: context.correlationId,
        caseId: context.caseId,
        userId: context.userId,
        languageCode: context.languageCode,
        redactSensitiveEntitiesBeforeSend:
            context.redactSensitiveEntitiesBeforeSend,
      ),
    );
    return enqueueActionForTranscript(
      action: action,
      transcript: transcript,
      speechStartedAt: speechStartedAt,
    );
  }

  VoiceTranscriptResult enqueueActionForTranscript({
    required RuleEngineAction action,
    required String transcript,
    required DateTime speechStartedAt,
  }) {
    if (action is IgnoreRuleAction) {
      return const VoiceTranscriptResult(
        accepted: true,
        duplicate: false,
        queuedAction: null,
      );
    }

    final idempotencyKey = buildIdempotencyKey(
      speechStartedAt: speechStartedAt,
      transcript: transcript,
    );
    if (_processedIdempotencyKeys.contains(idempotencyKey)) {
      return const VoiceTranscriptResult(
        accepted: true,
        duplicate: true,
        queuedAction: null,
      );
    }
    _processedIdempotencyKeys.add(idempotencyKey);
    final queued = QueuedVoiceSessionAction(
      action: action,
      idempotencyKey: idempotencyKey,
      originalTranscript: transcript.trim(),
    );
    _actionQueue.add(queued);
    awaitingConfirmation = false;
    pendingIntent = null;
    draftMessage = null;
    _continueDraftAfterNo = false;
    _silenceTimer?.cancel();
    _silenceTimer = null;
    _setPhase(VoiceSessionPhase.processing);
    return VoiceTranscriptResult(
      accepted: true,
      duplicate: false,
      queuedAction: queued,
    );
  }

  QueuedVoiceSessionAction? dequeueAction() {
    if (_actionQueue.isEmpty) {
      if (!awaitingConfirmation) {
        _setPhase(
            isListening ? VoiceSessionPhase.listening : VoiceSessionPhase.idle);
      }
      return null;
    }
    _setPhase(VoiceSessionPhase.processing);
    return _actionQueue.removeFirst();
  }

  bool checkInactivity({
    required DateTime now,
    required RuleEngineContext context,
  }) {
    if (_actionQueue.isNotEmpty) {
      return false;
    }
    final lastSpeech = lastUserSpeechAt;
    if (!isListening || lastSpeech == null) {
      return false;
    }
    if (now.difference(lastSpeech) < silenceThreshold) {
      return false;
    }
    _handleSilenceThreshold(context: context);
    return true;
  }

  String buildIdempotencyKey({
    required DateTime speechStartedAt,
    required String transcript,
  }) {
    return '${speechStartedAt.toUtc().microsecondsSinceEpoch}:'
        '${_normalizeTranscript(transcript)}';
  }

  void _handleSilenceThreshold({required RuleEngineContext context}) {
    if (_actionQueue.isNotEmpty) {
      return;
    }
    final draft = (draftMessage ?? '').trim();
    if (draft.isEmpty) {
      _scheduleSilenceTimer();
      return;
    }

    final repeatedPrompt = awaitingConfirmation;
    if (!awaitingConfirmation) {
      final action = _ruleEngine.evaluate(
        input: draft,
        context: RuleEngineContext(
          awaitingProfileName: context.awaitingProfileName,
          awaitingProfileField: context.awaitingProfileField,
          awaitingProfilePatchConfirmation:
              context.awaitingProfilePatchConfirmation,
          awaitingCaseArchiveConfirmation:
              context.awaitingCaseArchiveConfirmation,
          awaitingCaseTitle: context.awaitingCaseTitle,
          submitMessageWhenNoRuleMatches: true,
          pendingProfilePatch: context.pendingProfilePatch,
          currentDraft: context.currentDraft ?? draft,
          lastDictatedDraft: context.lastDictatedDraft ?? draft,
          correlationId: context.correlationId,
          caseId: context.caseId,
          userId: context.userId,
          languageCode: context.languageCode,
          redactSensitiveEntitiesBeforeSend:
              context.redactSensitiveEntitiesBeforeSend,
        ),
      );
      if (action is! IgnoreRuleAction) {
        pendingIntent = action;
        awaitingConfirmation = true;
        _setPhase(VoiceSessionPhase.awaitingConfirmation);
      }
    }

    if (awaitingConfirmation) {
      onSilenceThresholdReached?.call(
        VoiceSilenceThresholdEvent(
          prompt: confirmationPromptForLanguage?.call(context.languageCode) ??
              voiceSessionConfirmationPrompt,
          draftMessage: draft,
          repeatedPrompt: repeatedPrompt,
        ),
      );
    }
    lastUserSpeechAt = DateTime.now();
    _scheduleSilenceTimer();
  }

  VoiceTranscriptResult _confirmPendingIntent({
    required String transcript,
    required DateTime speechStartedAt,
  }) {
    final action = pendingIntent;
    _clearPendingIntent();
    if (action == null) {
      return const VoiceTranscriptResult(
        accepted: true,
        duplicate: false,
        queuedAction: null,
      );
    }
    return enqueueActionForTranscript(
      action: action,
      transcript: draftMessage ?? transcript,
      speechStartedAt: speechStartedAt,
    );
  }

  void _clearPendingIntent() {
    awaitingConfirmation = false;
    pendingIntent = null;
    _continueDraftAfterNo = false;
    draftMessage = null;
    _setPhase(
        isListening ? VoiceSessionPhase.listening : VoiceSessionPhase.idle);
    _scheduleSilenceTimer();
  }

  void _continuePendingDraft() {
    awaitingConfirmation = false;
    pendingIntent = null;
    _continueDraftAfterNo = true;
    _setPhase(
        isListening ? VoiceSessionPhase.listening : VoiceSessionPhase.idle);
    lastUserSpeechAt = DateTime.now();
    _scheduleSilenceTimer();
  }

  String _resolveDraftTranscript(String transcript) {
    if (!_continueDraftAfterNo) {
      return transcript;
    }
    final existing = (draftMessage ?? '').trim();
    if (existing.isEmpty) {
      return transcript;
    }
    if (transcript.isEmpty) {
      return existing;
    }
    final normalizedExisting = _normalizeTranscript(existing);
    final normalizedTranscript = _normalizeTranscript(transcript);
    if (normalizedTranscript == normalizedExisting ||
        normalizedTranscript.startsWith(normalizedExisting)) {
      return transcript;
    }
    if (normalizedExisting.endsWith(normalizedTranscript)) {
      return existing;
    }
    return '$existing $transcript';
  }

  void _scheduleSilenceTimer() {
    _silenceTimer?.cancel();
    if (!isListening || draftMessage == null || draftMessage!.trim().isEmpty) {
      return;
    }
    _silenceTimer = Timer(silenceThreshold, () {
      _handleSilenceThreshold(
        context: RuleEngineContext(
          awaitingProfileName: false,
          awaitingProfileField: false,
          awaitingProfilePatchConfirmation: false,
          awaitingCaseArchiveConfirmation: false,
          awaitingCaseTitle: false,
          submitMessageWhenNoRuleMatches: true,
          pendingProfilePatch: null,
          currentDraft: draftMessage,
          lastDictatedDraft: draftMessage,
        ),
      );
    });
  }

  void _setPhase(VoiceSessionPhase nextPhase) {
    if (phase == nextPhase) {
      return;
    }
    phase = nextPhase;
    onStateChanged?.call();
  }

  String _normalizeTranscript(String value) {
    return value.trim().toLowerCase().replaceAll(RegExp(r'\s+'), ' ');
  }

  bool _hasExplicitExecutionTerminator(String normalizedTranscript) {
    return isSpokenSendCommand(normalizedTranscript) ||
        hasTrailingSpokenSendCommand(normalizedTranscript);
  }
}

typedef VoidCallback = void Function();
