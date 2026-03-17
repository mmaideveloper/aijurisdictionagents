import 'package:flutter_tts/flutter_tts.dart';

class JurisdictaSpeakerVoice {
  const JurisdictaSpeakerVoice({
    required this.id,
    required this.name,
    required this.locale,
    required this.config,
  });

  final String id;
  final String name;
  final String locale;
  final Map<String, String> config;
}

abstract class JurisdictaSpeaker {
  Future<bool> initialize();
  Future<List<JurisdictaSpeakerVoice>> listVoices({
    required String languageCode,
  });
  Future<void> selectVoice({
    required String languageCode,
    required String? voiceId,
  });
  String? selectedVoiceIdFor({
    required String languageCode,
  });
  Future<bool> speak({
    required String text,
    required String languageCode,
  });
  Future<void> stop();
}

JurisdictaSpeaker createJurisdictaSpeaker() {
  return _FlutterTtsJurisdictaSpeaker();
}

class _FlutterTtsJurisdictaSpeaker implements JurisdictaSpeaker {
  final FlutterTts _tts = FlutterTts();
  bool _initialized = false;
  bool _available = true;
  final Map<String, List<JurisdictaSpeakerVoice>> _voicesByLocale =
      <String, List<JurisdictaSpeakerVoice>>{};
  final Map<String, String?> _selectedVoiceIdByLocale = <String, String?>{};

  @override
  Future<bool> initialize() async {
    if (_initialized) {
      return _available;
    }
    try {
      await _tts.awaitSpeakCompletion(true);
      await _tts.setSpeechRate(0.5);
      await _tts.setPitch(1.0);
      await _tts.setVolume(1.0);
      _initialized = true;
      return true;
    } catch (_) {
      _available = false;
      _initialized = true;
      return false;
    }
  }

  @override
  Future<List<JurisdictaSpeakerVoice>> listVoices({
    required String languageCode,
  }) async {
    final ready = await initialize();
    if (!ready) {
      return const <JurisdictaSpeakerVoice>[];
    }

    final locale = _ttsLocale(languageCode);
    final cached = _voicesByLocale[locale];
    if (cached != null) {
      return cached;
    }

    try {
      final voices = await _tts.getVoices;
      final resolved = _pickVoices(voices, locale);
      _voicesByLocale[locale] = resolved;
      if (!_selectedVoiceIdByLocale.containsKey(locale)) {
        _selectedVoiceIdByLocale[locale] =
            resolved.isNotEmpty ? _preferDefaultVoice(resolved, locale).id : null;
      }
      return resolved;
    } catch (_) {
      return const <JurisdictaSpeakerVoice>[];
    }
  }

  @override
  Future<void> selectVoice({
    required String languageCode,
    required String? voiceId,
  }) async {
    final locale = _ttsLocale(languageCode);
    final voices = await listVoices(languageCode: languageCode);
    if (voiceId == null || voiceId.isEmpty) {
      _selectedVoiceIdByLocale[locale] =
          voices.isNotEmpty ? _preferDefaultVoice(voices, locale).id : null;
      return;
    }

    final exists = voices.any((voice) => voice.id == voiceId);
    if (exists) {
      _selectedVoiceIdByLocale[locale] = voiceId;
    }
  }

  @override
  String? selectedVoiceIdFor({
    required String languageCode,
  }) {
    return _selectedVoiceIdByLocale[_ttsLocale(languageCode)];
  }

  @override
  Future<bool> speak({
    required String text,
    required String languageCode,
  }) async {
    final message = text.trim();
    if (message.isEmpty) {
      return false;
    }
    final ready = await initialize();
    if (!ready) {
      return false;
    }
    try {
      final locale = _ttsLocale(languageCode);
      final voices = await listVoices(languageCode: languageCode);
      final selectedVoiceId = _selectedVoiceIdByLocale[locale];
      final voice = voices
          .cast<JurisdictaSpeakerVoice?>()
          .firstWhere(
            (item) => item?.id == selectedVoiceId,
            orElse: () =>
                voices.isNotEmpty ? _preferDefaultVoice(voices, locale) : null,
          )
          ?.config;
      await _tts.stop();
      await _tts.setLanguage(locale);
      if (voice != null && voice.isNotEmpty) {
        await _tts.setVoice(voice);
      }
      await _tts.speak(message);
      return true;
    } catch (_) {
      _available = false;
      return false;
    }
  }

  @override
  Future<void> stop() async {
    if (!_initialized || !_available) {
      return;
    }
    try {
      await _tts.stop();
    } catch (_) {}
  }

  String _ttsLocale(String languageCode) {
    switch (languageCode.trim().toUpperCase()) {
      case 'SK':
        return 'sk-SK';
      case 'CS':
        return 'cs-CZ';
      case 'DE':
      case 'GE':
        return 'de-DE';
      case 'EN':
      default:
        return 'en-US';
    }
  }

  List<JurisdictaSpeakerVoice> _pickVoices(dynamic voices, String locale) {
    if (voices is! List) {
      return const <JurisdictaSpeakerVoice>[];
    }

    final normalizedLocale = locale.toLowerCase();
    final exactMatches = <JurisdictaSpeakerVoice>[];
    final languageMatches = <JurisdictaSpeakerVoice>[];

    for (final item in voices) {
      if (item is! Map) {
        continue;
      }

      final normalizedVoice = <String, String>{};
      item.forEach((key, value) {
        if (key is String && value is String) {
          normalizedVoice[key] = value;
        }
      });

      final voiceLocale = (normalizedVoice['locale'] ?? '').toLowerCase();
      if (voiceLocale.isEmpty) {
        continue;
      }
      final voiceName = normalizedVoice['name'] ?? voiceLocale;
      final speakerVoice = JurisdictaSpeakerVoice(
        id: '$voiceLocale::$voiceName',
        name: voiceName,
        locale: normalizedVoice['locale'] ?? locale,
        config: normalizedVoice,
      );

      if (voiceLocale == normalizedLocale) {
        exactMatches.add(speakerVoice);
        continue;
      }

      if (voiceLocale.startsWith('${normalizedLocale.split('-').first}-')) {
        languageMatches.add(speakerVoice);
      }
    }

    final preferred = exactMatches.isNotEmpty ? exactMatches : languageMatches;
    preferred.sort(
      (left, right) =>
          _voiceRank(right, locale).compareTo(_voiceRank(left, locale)),
    );
    return preferred;
  }

  JurisdictaSpeakerVoice _preferDefaultVoice(
    List<JurisdictaSpeakerVoice> voices,
    String targetLocale,
  ) {
    if (targetLocale.toLowerCase() == 'sk-sk') {
      final preferredSkVoice = voices
          .cast<JurisdictaSpeakerVoice?>()
          .firstWhere(
            (voice) =>
                voice != null &&
                voice.locale.toLowerCase() == 'sk-sk' &&
                voice.name.toLowerCase().contains('sk_sk-language'),
            orElse: () => null,
          );
      if (preferredSkVoice != null) {
        return preferredSkVoice;
      }
    }
    return voices.first;
  }

  int _voiceRank(JurisdictaSpeakerVoice voice, String targetLocale) {
    final name = voice.name.toLowerCase();
    final locale = voice.locale.toLowerCase();
    var score = 0;
    score += _localePreferenceScore(locale, targetLocale);
    if (name.contains('local')) {
      score += 100;
    }
    if (name.contains('natural')) {
      score += 50;
    }
    if (name.contains('standard')) {
      score += 30;
    }
    if (name.contains('hochdeutsch')) {
      score += 30;
    }
    if (name.contains('deutsch') || name.contains('german')) {
      score += 20;
    }
    if (name.contains('female') || name.contains('woman')) {
      score += 20;
    }
    if (name.contains('male') || name.contains('man')) {
      score += 10;
    }
    return score;
  }

  int _localePreferenceScore(String voiceLocale, String targetLocale) {
    final normalizedTarget = targetLocale.toLowerCase();
    if (voiceLocale == normalizedTarget) {
      return 500;
    }

    final fallbacks = _localeFallbacks(normalizedTarget);
    final fallbackIndex = fallbacks.indexOf(voiceLocale);
    if (fallbackIndex >= 0) {
      return 400 - (fallbackIndex * 25);
    }

    if (voiceLocale.startsWith('${normalizedTarget.split('-').first}-')) {
      return 200;
    }

    return 0;
  }

  List<String> _localeFallbacks(String targetLocale) {
    switch (targetLocale) {
      case 'de-de':
        return const <String>['de-at', 'de-ch'];
      case 'sk-sk':
        return const <String>['cs-cz'];
      default:
        return const <String>[];
    }
  }
}
