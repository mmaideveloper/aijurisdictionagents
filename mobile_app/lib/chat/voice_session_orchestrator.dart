import 'dart:async';

import 'rule_engine.dart';

class VoiceSessionState {
  const VoiceSessionState({
    required this.isListening,
    required this.awaitingConfirmation,
    this.pendingIntent,
    this.lastTranscriptId,
  });

  final bool isListening;
  final bool awaitingConfirmation;
  final String? pendingIntent;
  final String? lastTranscriptId;
}

class VoiceSessionEvent {
  const VoiceSessionEvent(this.type, {this.payload});

  final String type;
  final String? payload;
}

class VoiceSessionOrchestrator {
  VoiceSessionOrchestrator({
    required this.ruleEngine,
    this.silenceThreshold = const Duration(seconds: 10),
    void Function(VoiceSessionEvent event)? onEvent,
  }) : _onEvent = onEvent;

  final RuleEngine ruleEngine;
  final Duration silenceThreshold;
  final void Function(VoiceSessionEvent event)? _onEvent;

  Timer? _silenceTimer;
  String? _lastTranscriptId;
  bool _awaitingConfirmation = false;
  bool _isListening = false;
  String? _pendingIntent;

  VoiceSessionState get state => VoiceSessionState(
        isListening: _isListening,
        awaitingConfirmation: _awaitingConfirmation,
        pendingIntent: _pendingIntent,
        lastTranscriptId: _lastTranscriptId,
      );

  void startListening() {
    _isListening = true;
    _awaitingConfirmation = false;
    _restartTimer();
    _emit(const VoiceSessionEvent('listening_started'));
  }

  void stopListening() {
    _isListening = false;
    _awaitingConfirmation = false;
    _silenceTimer?.cancel();
    _silenceTimer = null;
    _emit(const VoiceSessionEvent('listening_stopped'));
  }

  RuleEngineAction onTranscript({
    required String transcript,
    required RuleEngineContext context,
    required int timestampMs,
    bool isFinal = true,
  }) {
    if (!_isListening) {
      return const IgnoreRuleAction();
    }

    final normalized = transcript.trim().toLowerCase();
    final transcriptId = '$timestampMs:$normalized';
    if (_lastTranscriptId == transcriptId) {
      return const IgnoreRuleAction();
    }
    _lastTranscriptId = transcriptId;
    _awaitingConfirmation = false;
    _restartTimer();

    if (!isFinal) {
      return const IgnoreRuleAction();
    }

    final action = ruleEngine.evaluate(input: transcript, context: context);
    _pendingIntent = _resolvePendingIntent(action);
    if (_pendingIntent != null) {
      _emit(VoiceSessionEvent('intent_detected', payload: _pendingIntent));
    }
    return action;
  }

  void confirmPendingIntent(bool confirmed) {
    if (!_isListening) {
      return;
    }
    _awaitingConfirmation = false;
    _emit(VoiceSessionEvent(
      confirmed ? 'intent_confirmed' : 'intent_rejected',
      payload: _pendingIntent,
    ));
    if (!confirmed) {
      _pendingIntent = null;
    }
    _restartTimer();
  }

  void dispose() {
    _isListening = false;
    _silenceTimer?.cancel();
  }

  void _restartTimer() {
    _silenceTimer?.cancel();
    if (!_isListening) {
      return;
    }
    _silenceTimer = Timer(silenceThreshold, () {
      if (!_isListening) {
        return;
      }
      _awaitingConfirmation = true;
      _emit(const VoiceSessionEvent('silence_threshold_reached'));
    });
  }

  String? _resolvePendingIntent(RuleEngineAction action) {
    if (action is CreateCaseRuleAction) {
      return 'create_case';
    }
    if (action is SubmitMessageRuleAction || action is SendCurrentDraftRuleAction) {
      return 'submit_message';
    }
    if (action is StoreProfileNameRuleAction) {
      return 'update_profile_name';
    }
    return null;
  }

  void _emit(VoiceSessionEvent event) {
    _onEvent?.call(event);
  }
}
