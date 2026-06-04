import 'dart:convert';
import 'dart:math';

enum VoiceLoopbackRuntime {
  localDevice,
  azure,
}

extension VoiceLoopbackRuntimeLabel on VoiceLoopbackRuntime {
  String get label {
    switch (this) {
      case VoiceLoopbackRuntime.localDevice:
        return 'local-device';
      case VoiceLoopbackRuntime.azure:
        return 'azure';
    }
  }
}

class VoiceLoopbackTurn {
  const VoiceLoopbackTurn({
    required this.turnNumber,
    required this.role,
    required this.sourceText,
    required this.ttsText,
    required this.sttTranscript,
    required this.similarityScore,
    required this.truncated,
    required this.interrupted,
    required this.startedAtUtc,
    required this.completedAtUtc,
    required this.runtimeMode,
  });

  final int turnNumber;
  final String role;
  final String sourceText;
  final String ttsText;
  final String sttTranscript;
  final double similarityScore;
  final bool truncated;
  final bool interrupted;
  final DateTime startedAtUtc;
  final DateTime completedAtUtc;
  final VoiceLoopbackRuntime runtimeMode;

  bool get passed {
    return sourceText.trim().isNotEmpty &&
        ttsText.trim().isNotEmpty &&
        sttTranscript.trim().isNotEmpty &&
        similarityScore >= VoiceLoopbackConversation.minimumSimilarityScore &&
        !truncated &&
        !interrupted;
  }

  Map<String, Object?> toJson() {
    return <String, Object?>{
      'turn_number': turnNumber,
      'role': role,
      'source_text': sourceText,
      'tts_text': ttsText,
      'stt_transcript': sttTranscript,
      'similarity_score': similarityScore,
      'truncated': truncated,
      'interrupted': interrupted,
      'started_at_utc': startedAtUtc.toIso8601String(),
      'completed_at_utc': completedAtUtc.toIso8601String(),
      'runtime_mode': runtimeMode.label,
      'raw_audio_persisted': false,
    };
  }
}

class VoiceLoopbackConversation {
  const VoiceLoopbackConversation({
    required this.caseTitle,
    required this.runtimeMode,
    required this.questionAnswerPairs,
    required this.turns,
    required this.startedAtUtc,
    required this.completedAtUtc,
  });

  static const double minimumSimilarityScore = 0.92;

  final String caseTitle;
  final VoiceLoopbackRuntime runtimeMode;
  final int questionAnswerPairs;
  final List<VoiceLoopbackTurn> turns;
  final DateTime startedAtUtc;
  final DateTime completedAtUtc;

  bool get completedExpectedTurns {
    return turns.length == questionAnswerPairs * 2;
  }

  bool get passed {
    return caseTitle.startsWith('simulacia ') &&
        questionAnswerPairs == 10 &&
        completedExpectedTurns &&
        turns.every((turn) => turn.passed);
  }

  Map<String, Object?> toJson() {
    return <String, Object?>{
      'schema_version': 1,
      'case_title': caseTitle,
      'runtime_mode': runtimeMode.label,
      'question_answer_pairs': questionAnswerPairs,
      'turn_count': turns.length,
      'expected_turn_count': questionAnswerPairs * 2,
      'passed': passed,
      'minimum_similarity_score': minimumSimilarityScore,
      'started_at_utc': startedAtUtc.toIso8601String(),
      'completed_at_utc': completedAtUtc.toIso8601String(),
      'privacy': <String, Object?>{
        'raw_audio_persisted': false,
        'artifact_contains_transcripts': true,
        'purpose': 'local deterministic voice loopback regression test',
      },
      'turns': turns.map((turn) => turn.toJson()).toList(growable: false),
    };
  }

  String toPrettyJson() {
    return const JsonEncoder.withIndent('  ').convert(toJson());
  }
}

class VoiceLoopbackSimilarity {
  const VoiceLoopbackSimilarity();

  double score(String expected, String actual) {
    final normalizedExpected = normalize(expected);
    final normalizedActual = normalize(actual);
    if (normalizedExpected.isEmpty || normalizedActual.isEmpty) {
      return 0;
    }
    if (normalizedExpected == normalizedActual) {
      return 1;
    }
    final maxLength = max(normalizedExpected.length, normalizedActual.length);
    final distance = _levenshtein(normalizedExpected, normalizedActual);
    return double.parse((1 - (distance / maxLength)).toStringAsFixed(4));
  }

  bool isTruncated(String expected, String actual) {
    final normalizedExpected = normalize(expected);
    final normalizedActual = normalize(actual);
    if (normalizedExpected.isEmpty || normalizedActual.isEmpty) {
      return true;
    }
    if (normalizedExpected == normalizedActual) {
      return false;
    }
    final lengthRatio = normalizedActual.length / normalizedExpected.length;
    return lengthRatio < 0.85 &&
        normalizedExpected.startsWith(normalizedActual);
  }

  String normalize(String value) {
    final lower = value.toLowerCase();
    final withoutAccents = lower.split('').map(_stripAccent).join();
    return withoutAccents
        .replaceAll(RegExp(r'[^a-z0-9 ]+'), ' ')
        .replaceAll(RegExp(r'\s+'), ' ')
        .trim();
  }

  int _levenshtein(String left, String right) {
    if (left == right) {
      return 0;
    }
    if (left.isEmpty) {
      return right.length;
    }
    if (right.isEmpty) {
      return left.length;
    }

    var previous = List<int>.generate(right.length + 1, (index) => index);
    for (var i = 0; i < left.length; i += 1) {
      final current = List<int>.filled(right.length + 1, 0);
      current[0] = i + 1;
      for (var j = 0; j < right.length; j += 1) {
        final insertion = current[j] + 1;
        final deletion = previous[j + 1] + 1;
        final substitution = previous[j] + (left[i] == right[j] ? 0 : 1);
        current[j + 1] = min(insertion, min(deletion, substitution));
      }
      previous = current;
    }
    return previous[right.length];
  }

  String _stripAccent(String char) {
    const replacements = <String, String>{
      'á': 'a',
      'ä': 'a',
      'č': 'c',
      'ď': 'd',
      'é': 'e',
      'í': 'i',
      'ĺ': 'l',
      'ľ': 'l',
      'ň': 'n',
      'ó': 'o',
      'ô': 'o',
      'ŕ': 'r',
      'š': 's',
      'ť': 't',
      'ú': 'u',
      'ý': 'y',
      'ž': 'z',
    };
    return replacements[char] ?? char;
  }
}

abstract class VoiceLoopbackSpeaker {
  Future<String> speak(String text);
}

abstract class VoiceLoopbackRecognizer {
  Future<String> recognize(String spokenText);
}

class DeterministicVoiceLoopbackSpeaker implements VoiceLoopbackSpeaker {
  const DeterministicVoiceLoopbackSpeaker();

  @override
  Future<String> speak(String text) async {
    return text.trim();
  }
}

class DeterministicVoiceLoopbackRecognizer implements VoiceLoopbackRecognizer {
  const DeterministicVoiceLoopbackRecognizer({
    this.transcriptTransform,
  });

  final String Function(String value)? transcriptTransform;

  @override
  Future<String> recognize(String spokenText) async {
    return (transcriptTransform ?? _identity)(spokenText.trim());
  }

  static String _identity(String value) => value;
}

class VoiceLoopbackHarness {
  VoiceLoopbackHarness({
    required this.runtimeMode,
    VoiceLoopbackSpeaker speaker = const DeterministicVoiceLoopbackSpeaker(),
    VoiceLoopbackRecognizer recognizer =
        const DeterministicVoiceLoopbackRecognizer(),
    VoiceLoopbackSimilarity similarity = const VoiceLoopbackSimilarity(),
    int Function()? randomNumberFactory,
    DateTime Function()? clock,
  })  : _speaker = speaker,
        _recognizer = recognizer,
        _similarity = similarity,
        _randomNumberFactory =
            randomNumberFactory ?? (() => Random().nextInt(900000) + 100000),
        _clock = clock ?? (() => DateTime.now().toUtc());

  final VoiceLoopbackRuntime runtimeMode;
  final VoiceLoopbackSpeaker _speaker;
  final VoiceLoopbackRecognizer _recognizer;
  final VoiceLoopbackSimilarity _similarity;
  final int Function() _randomNumberFactory;
  final DateTime Function() _clock;

  Future<VoiceLoopbackConversation> run({int questionAnswerPairs = 10}) async {
    if (questionAnswerPairs <= 0) {
      throw ArgumentError.value(
        questionAnswerPairs,
        'questionAnswerPairs',
        'Must be greater than zero.',
      );
    }

    final startedAt = _clock();
    final caseTitle = 'simulacia ${_randomNumberFactory()}';
    final turns = <VoiceLoopbackTurn>[];
    for (var pairIndex = 0; pairIndex < questionAnswerPairs; pairIndex += 1) {
      final questionNumber = pairIndex + 1;
      turns.add(
        await _roundTrip(
          turnNumber: turns.length + 1,
          role: 'system',
          text: _systemQuestion(questionNumber, caseTitle),
        ),
      );
      turns.add(
        await _roundTrip(
          turnNumber: turns.length + 1,
          role: 'ai_simulator',
          text: _simulatorAnswer(questionNumber, caseTitle),
        ),
      );
    }

    return VoiceLoopbackConversation(
      caseTitle: caseTitle,
      runtimeMode: runtimeMode,
      questionAnswerPairs: questionAnswerPairs,
      turns: turns,
      startedAtUtc: startedAt,
      completedAtUtc: _clock(),
    );
  }

  Future<VoiceLoopbackTurn> _roundTrip({
    required int turnNumber,
    required String role,
    required String text,
  }) async {
    final startedAt = _clock();
    final ttsText = await _speaker.speak(text);
    final transcript = await _recognizer.recognize(ttsText);
    final score = _similarity.score(text, transcript);
    return VoiceLoopbackTurn(
      turnNumber: turnNumber,
      role: role,
      sourceText: text,
      ttsText: ttsText,
      sttTranscript: transcript,
      similarityScore: score,
      truncated: _similarity.isTruncated(text, transcript),
      interrupted: transcript.trim().isEmpty || ttsText.trim().isEmpty,
      startedAtUtc: startedAt,
      completedAtUtc: _clock(),
      runtimeMode: runtimeMode,
    );
  }

  String _systemQuestion(int questionNumber, String caseTitle) {
    return 'Otazka $questionNumber pre pripad $caseTitle: '
        'opiste pravny problem a povedzte odpoved cislo $questionNumber.';
  }

  String _simulatorAnswer(int answerNumber, String caseTitle) {
    return 'Odpoved $answerNumber pre $caseTitle: '
        'AI simulator poskytuje testovacie fakty a caka na dalsiu otazku.';
  }
}
