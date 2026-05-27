import 'dart:io';

import 'package:ai_jurisdiction_mobile/chat/voice_loopback_test_harness.dart';
import 'package:flutter_test/flutter_test.dart';

const String _runtimeDefine = String.fromEnvironment(
  'AIJ_VOICE_LOOPBACK_RUNTIME',
  defaultValue: 'local-device',
);
const int _turnCountDefine = int.fromEnvironment(
  'AIJ_VOICE_LOOPBACK_TURN_COUNT',
  defaultValue: 10,
);

void main() {
  group('VoiceLoopbackSimilarity', () {
    const similarity = VoiceLoopbackSimilarity();

    test('normalizes Slovak accents and punctuation', () {
      expect(
        similarity.score(
          'Mozem uz odpovedat na otazku?',
          'Môžem už odpovedať na otázku.',
        ),
        1,
      );
    });

    test('detects materially truncated transcripts', () {
      expect(
        similarity.isTruncated(
          'AI simulator poskytuje testovacie fakty a caka na dalsiu otazku.',
          'AI simulator poskytuje testovacie',
        ),
        isTrue,
      );
    });
  });

  group('VoiceLoopbackHarness', () {
    test('completes ten deterministic question and answer pairs', () async {
      final runtime = _runtimeFromDefine(_runtimeDefine);
      final harness = VoiceLoopbackHarness(
        runtimeMode: runtime,
        randomNumberFactory: () => 424242,
        clock: _FixedClock(DateTime.utc(2026, 5, 27, 12)).call,
      );

      final conversation =
          await harness.run(questionAnswerPairs: _turnCountDefine);

      expect(conversation.caseTitle, 'simulacia 424242');
      expect(conversation.questionAnswerPairs, 10);
      expect(conversation.turns, hasLength(20));
      expect(conversation.completedExpectedTurns, isTrue);
      expect(conversation.passed, isTrue);
      expect(
        conversation.turns.every((turn) => turn.rawAudioPersisted == false),
        isTrue,
      );

      await _writeArtifact(conversation);
    });

    test('fails a turn when STT transcript is interrupted', () async {
      final harness = VoiceLoopbackHarness(
        runtimeMode: VoiceLoopbackRuntime.localDevice,
        randomNumberFactory: () => 111111,
        recognizer: const DeterministicVoiceLoopbackRecognizer(
          transcriptTransform: _truncateAfterThreeWords,
        ),
      );

      final conversation = await harness.run(questionAnswerPairs: 1);

      expect(conversation.completedExpectedTurns, isTrue);
      expect(conversation.passed, isFalse);
      expect(conversation.turns.any((turn) => turn.truncated), isTrue);
    });
  });
}

VoiceLoopbackRuntime _runtimeFromDefine(String value) {
  switch (value.trim().toLowerCase()) {
    case 'azure':
      return VoiceLoopbackRuntime.azure;
    case 'local':
    case 'local-device':
    default:
      return VoiceLoopbackRuntime.localDevice;
  }
}

String _truncateAfterThreeWords(String value) {
  return value.split(RegExp(r'\s+')).take(3).join(' ');
}

Future<void> _writeArtifact(VoiceLoopbackConversation conversation) async {
  final artifactDir = Platform.environment['AIJ_VOICE_LOOPBACK_ARTIFACT_DIR'];
  if (artifactDir == null || artifactDir.trim().isEmpty) {
    return;
  }
  final directory = Directory(artifactDir);
  if (!directory.existsSync()) {
    directory.createSync(recursive: true);
  }
  final file = File(
    '${directory.path}${Platform.pathSeparator}'
    'voice-loopback-${conversation.runtimeMode.label}.json',
  );
  await file.writeAsString(conversation.toPrettyJson());
}

class _FixedClock {
  _FixedClock(this._current);

  DateTime _current;

  DateTime call() {
    final value = _current;
    _current = _current.add(const Duration(milliseconds: 250));
    return value;
  }
}

extension on VoiceLoopbackTurn {
  bool get rawAudioPersisted {
    final json = toJson();
    return json['raw_audio_persisted'] == true;
  }
}
