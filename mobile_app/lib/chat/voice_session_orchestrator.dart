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
  String? _pendingIntent;

  VoiceSessionState get state => VoiceSessionState(
        isListening: _silenceTimer != null,
        awaitingConfirmation: _awaitingConfirmation,
        pendingIntent: _pendingIntent,
        lastTranscriptId: _lastTranscriptId,
      );

  void startListening() {
    _restartTimer();
    _emit(const VoiceSessionEvent('listening_started'));
  }

  void stopListening() {
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
    final normalized = transcript.trim().toLowerCase();
    final transcriptId = '$timestampMs:$normalized';
    if (_lastTranscriptId == transcriptId) {
      return const IgnoreRuleAction();
    }
    _lastTranscriptId = transcriptId;
    _restartTimer();

    if (!isFinal) {
      return const IgnoreRuleAction();
    }

    final action = ruleEngine.evaluate(input: transcript, context: context);
    if (action is CreateCaseRuleAction) {
      _pendingIntent = 'create_case';
    }
    if (action is SubmitMessageRuleAction) {
      _pendingIntent = 'submit_message';
    }
    return action;
  }

  void confirmPendingIntent(bool confirmed) {
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
    _silenceTimer?.cancel();
  }

  void _restartTimer() {
    _silenceTimer?.cancel();
    _silenceTimer = Timer(silenceThreshold, () {
      _awaitingConfirmation = true;
      _emit(const VoiceSessionEvent('silence_threshold_reached'));
    });
  }

  void _emit(VoiceSessionEvent event) {
    _onEvent?.call(event);
  }
}
