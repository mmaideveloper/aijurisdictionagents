import 'package:ai_jurisdiction_mobile/chat/rule_engine.dart';
import 'package:ai_jurisdiction_mobile/chat/voice_session_orchestrator.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('deduplicates repeated transcript ids', () {
    final orchestrator = VoiceSessionOrchestrator(ruleEngine: const RuleEngine());
    const context = RuleEngineContext(
      awaitingProfileName: false,
      awaitingCaseArchiveConfirmation: false,
      awaitingCaseTitle: false,
      submitMessageWhenNoRuleMatches: true,
    );

    final first = orchestrator.onTranscript(
      transcript: 'Please create a new case',
      context: context,
      timestampMs: 1000,
    );
    final second = orchestrator.onTranscript(
      transcript: 'Please create a new case',
      context: context,
      timestampMs: 1000,
    );

    expect(first, isA<CreateCaseRuleAction>());
    expect(second, isA<IgnoreRuleAction>());
  });

  test('emits silence event after threshold', () async {
    final events = <String>[];
    final orchestrator = VoiceSessionOrchestrator(
      ruleEngine: const RuleEngine(),
      silenceThreshold: const Duration(milliseconds: 50),
      onEvent: (event) => events.add(event.type),
    );

    orchestrator.startListening();
    await Future<void>.delayed(const Duration(milliseconds: 90));

    expect(events, contains('silence_threshold_reached'));
    expect(orchestrator.state.awaitingConfirmation, isTrue);
  });
}
