import 'package:ai_jurisdiction_mobile/chat/rule_engine.dart';
import 'package:ai_jurisdiction_mobile/chat/voice_session_orchestrator.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('VoiceSessionOrchestrator', () {
    const context = RuleEngineContext(
      awaitingProfileName: false,
      awaitingProfileField: false,
      awaitingProfilePatchConfirmation: false,
      awaitingCaseArchiveConfirmation: false,
      awaitingCaseTitle: false,
      submitMessageWhenNoRuleMatches: true,
      pendingProfilePatch: null,
    );

    test('keeps a flowing dictation draft without queuing partial actions', () {
      final startedAt = DateTime.utc(2026, 5, 15, 10);
      final orchestrator = VoiceSessionOrchestrator();

      orchestrator.startListening(now: startedAt);
      final partial = orchestrator.acceptTranscript(
        transcript: 'Potrebujem poradit',
        isFinal: false,
        speechStartedAt: startedAt,
        context: context,
        submitMessageWhenNoRuleMatches: false,
        receivedAt: startedAt.add(const Duration(seconds: 1)),
      );
      final finalResult = orchestrator.acceptTranscript(
        transcript: 'Potrebujem poradit so zmluvou posli',
        isFinal: true,
        speechStartedAt: startedAt,
        context: context,
        submitMessageWhenNoRuleMatches: true,
        receivedAt: startedAt.add(const Duration(seconds: 3)),
      );

      expect(partial.queuedAction, isNull);
      expect(orchestrator.draftMessage, 'Potrebujem poradit so zmluvou posli');
      expect(finalResult.queuedAction?.action, isA<SubmitMessageRuleAction>());
      expect(orchestrator.queuedActionCount, 1);

      final queued = orchestrator.dequeueAction();
      expect(
        (queued!.action as SubmitMessageRuleAction).message,
        'Potrebujem poradit so zmluvou',
      );
    });

    test('turns a silent draft into a confirmation prompt', () {
      final prompts = <VoiceSilenceThresholdEvent>[];
      final startedAt = DateTime.utc(2026, 5, 15, 11);
      final orchestrator = VoiceSessionOrchestrator(
        onSilenceThresholdReached: prompts.add,
      );

      orchestrator.startListening(now: startedAt);
      orchestrator.acceptTranscript(
        transcript: 'Potrebujem poradit so zmluvou',
        isFinal: false,
        speechStartedAt: startedAt,
        context: context,
        submitMessageWhenNoRuleMatches: false,
        receivedAt: startedAt,
      );

      final reached = orchestrator.checkInactivity(
        now: startedAt.add(const Duration(seconds: 10)),
        context: context,
      );

      expect(reached, isTrue);
      expect(orchestrator.awaitingConfirmation, isTrue);
      expect(orchestrator.phase, VoiceSessionPhase.awaitingConfirmation);
      expect(orchestrator.pendingIntent, isA<SubmitMessageRuleAction>());
      expect(prompts.single.prompt, voiceSessionConfirmationPrompt);
      expect(prompts.single.repeatedPrompt, isFalse);
      expect(orchestrator.queuedActionCount, 0);
    });

    test('queues a non-final case command with explicit send terminator', () {
      final prompts = <VoiceSilenceThresholdEvent>[];
      final startedAt = DateTime.utc(2026, 5, 15, 11, 30);
      final orchestrator = VoiceSessionOrchestrator(
        onSilenceThresholdReached: prompts.add,
      );

      orchestrator.startListening(now: startedAt);
      final result = orchestrator.acceptTranscript(
        transcript:
            'dobre potrebujem vytvorit novy pripad s nazvom splnomocnenie to je vsetko',
        isFinal: false,
        speechStartedAt: startedAt,
        context: context,
        submitMessageWhenNoRuleMatches: false,
        receivedAt: startedAt.add(const Duration(seconds: 1)),
      );
      final reached = orchestrator.checkInactivity(
        now: startedAt.add(const Duration(seconds: 12)),
        context: context,
      );

      expect(result.queuedAction?.action, isA<CreateCaseRuleAction>());
      expect(
        (result.queuedAction!.action as CreateCaseRuleAction).title,
        'splnomocnenie',
      );
      expect(orchestrator.phase, VoiceSessionPhase.processing);
      expect(orchestrator.awaitingConfirmation, isFalse);
      expect(reached, isFalse);
      expect(prompts, isEmpty);
    });

    test('uses explicit confirmation wording for silent drafts', () {
      expect(
        voiceSessionConfirmationPrompt,
        'Potvrď vykonanie požiadavky, povedz áno.',
      );
    });

    test('queues pending intent on yes and cancels it on no', () {
      final startedAt = DateTime.utc(2026, 5, 15, 12);
      final yesOrchestrator = VoiceSessionOrchestrator();

      yesOrchestrator.startListening(now: startedAt);
      yesOrchestrator.acceptTranscript(
        transcript: 'Potrebujem poradit so zmluvou',
        isFinal: false,
        speechStartedAt: startedAt,
        context: context,
        submitMessageWhenNoRuleMatches: false,
        receivedAt: startedAt,
      );
      yesOrchestrator.checkInactivity(
        now: startedAt.add(const Duration(seconds: 10)),
        context: context,
      );
      final yes = yesOrchestrator.acceptTranscript(
        transcript: 'áno',
        isFinal: true,
        speechStartedAt: startedAt,
        context: context,
        submitMessageWhenNoRuleMatches: true,
        receivedAt: startedAt.add(const Duration(seconds: 11)),
      );

      expect(yes.queuedAction?.action, isA<SubmitMessageRuleAction>());
      expect(yes.queuedAction?.originalTranscript,
          'Potrebujem poradit so zmluvou');
      expect(yesOrchestrator.awaitingConfirmation, isFalse);
      expect(yesOrchestrator.queuedActionCount, 1);

      final noOrchestrator = VoiceSessionOrchestrator();
      noOrchestrator.startListening(now: startedAt);
      noOrchestrator.acceptTranscript(
        transcript: 'Potrebujem poradit so zmluvou',
        isFinal: false,
        speechStartedAt: startedAt,
        context: context,
        submitMessageWhenNoRuleMatches: false,
        receivedAt: startedAt,
      );
      noOrchestrator.checkInactivity(
        now: startedAt.add(const Duration(seconds: 10)),
        context: context,
      );
      final no = noOrchestrator.acceptTranscript(
        transcript: 'nie',
        isFinal: true,
        speechStartedAt: startedAt,
        context: context,
        submitMessageWhenNoRuleMatches: true,
        receivedAt: startedAt.add(const Duration(seconds: 11)),
      );

      expect(no.queuedAction, isNull);
      expect(noOrchestrator.awaitingConfirmation, isFalse);
      expect(noOrchestrator.pendingIntent, isNull);
      expect(noOrchestrator.queuedActionCount, 0);
    });

    test('repeats timeout prompt without duplicating the pending action', () {
      final prompts = <VoiceSilenceThresholdEvent>[];
      final startedAt = DateTime.utc(2026, 5, 15, 13);
      final orchestrator = VoiceSessionOrchestrator(
        onSilenceThresholdReached: prompts.add,
      );

      orchestrator.startListening(now: startedAt);
      orchestrator.acceptTranscript(
        transcript: 'Potrebujem poradit so zmluvou',
        isFinal: false,
        speechStartedAt: startedAt,
        context: context,
        submitMessageWhenNoRuleMatches: false,
        receivedAt: startedAt,
      );

      orchestrator.checkInactivity(
        now: startedAt.add(const Duration(seconds: 10)),
        context: context,
      );
      orchestrator.checkInactivity(
        now: DateTime.now().add(const Duration(seconds: 11)),
        context: context,
      );

      expect(prompts, hasLength(2));
      expect(prompts.first.repeatedPrompt, isFalse);
      expect(prompts.last.repeatedPrompt, isTrue);
      expect(orchestrator.pendingIntent, isA<SubmitMessageRuleAction>());
      expect(orchestrator.queuedActionCount, 0);
    });

    test('deduplicates matching partial and final transcript submissions', () {
      final startedAt = DateTime.utc(2026, 5, 15, 14);
      final orchestrator = VoiceSessionOrchestrator();

      final first = orchestrator.acceptTranscript(
        transcript: 'Pošli',
        isFinal: true,
        speechStartedAt: startedAt,
        context: const RuleEngineContext(
          awaitingProfileName: false,
          awaitingProfileField: false,
          awaitingProfilePatchConfirmation: false,
          awaitingCaseArchiveConfirmation: false,
          awaitingCaseTitle: false,
          submitMessageWhenNoRuleMatches: true,
          pendingProfilePatch: null,
          currentDraft: 'Potrebujem poradit',
        ),
        submitMessageWhenNoRuleMatches: true,
        receivedAt: startedAt,
      );
      final duplicate = orchestrator.acceptTranscript(
        transcript: 'pošli',
        isFinal: true,
        speechStartedAt: startedAt,
        context: const RuleEngineContext(
          awaitingProfileName: false,
          awaitingProfileField: false,
          awaitingProfilePatchConfirmation: false,
          awaitingCaseArchiveConfirmation: false,
          awaitingCaseTitle: false,
          submitMessageWhenNoRuleMatches: true,
          pendingProfilePatch: null,
          currentDraft: 'Potrebujem poradit',
        ),
        submitMessageWhenNoRuleMatches: true,
        receivedAt: startedAt.add(const Duration(milliseconds: 20)),
      );

      expect(first.queuedAction?.action, isA<SendCurrentDraftRuleAction>());
      expect(duplicate.duplicate, isTrue);
      expect(orchestrator.queuedActionCount, 1);
    });

    test('deduplicates non-final terminator and matching final transcript', () {
      final startedAt = DateTime.utc(2026, 5, 15, 15);
      final orchestrator = VoiceSessionOrchestrator();

      final partial = orchestrator.acceptTranscript(
        transcript: 'Potrebujem poradit so zmluvou to je vsetko',
        isFinal: false,
        speechStartedAt: startedAt,
        context: context,
        submitMessageWhenNoRuleMatches: false,
        receivedAt: startedAt,
      );
      final finalResult = orchestrator.acceptTranscript(
        transcript: 'Potrebujem poradit so zmluvou to je vsetko',
        isFinal: true,
        speechStartedAt: startedAt,
        context: context,
        submitMessageWhenNoRuleMatches: true,
        receivedAt: startedAt.add(const Duration(milliseconds: 50)),
      );

      expect(partial.queuedAction?.action, isA<SubmitMessageRuleAction>());
      expect(finalResult.duplicate, isTrue);
      expect(orchestrator.queuedActionCount, 1);
    });
  });
}
