import 'dart:async';

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
  static const int _voiceRetryAttempts = 6;
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
    if (cached != null && cached.isNotEmpty) {
      return cached;
    }

    try {
      final voices = await _loadVoicesWithRetry(locale);
      final resolved = _pickVoices(voices, locale);
      if (resolved.isNotEmpty || cached == null) {
        _voicesByLocale[locale] = resolved;
      }
      if (!_selectedVoiceIdByLocale.containsKey(locale)) {
        _selectedVoiceIdByLocale[locale] = resolved.isNotEmpty
            ? _preferDefaultVoice(resolved, locale).id
            : null;
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
      final selectedVoice = voices.cast<JurisdictaSpeakerVoice?>().firstWhere(
            (item) => item?.id == selectedVoiceId,
            orElse: () =>
                voices.isNotEmpty ? _preferDefaultVoice(voices, locale) : null,
          );
      await _tts.stop();
      await _tts.setLanguage(selectedVoice?.locale ?? locale);
      final voice = selectedVoice?.config;
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

  Future<dynamic> _loadVoicesWithRetry(String locale) async {
    dynamic lastVoices = const <Object>[];
    for (var attempt = 0; attempt < _voiceRetryAttempts; attempt++) {
      lastVoices = await _tts.getVoices;
      if (_pickVoices(lastVoices, locale).isNotEmpty) {
        return lastVoices;
      }
      if (attempt < _voiceRetryAttempts - 1) {
        await Future<void>.delayed(
          Duration(milliseconds: 200 * (attempt + 1)),
        );
      }
    }
    return lastVoices;
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

    final normalizedLocale = _normalizeLocaleTag(locale);
    final preferredTags = _preferredVoiceTags(normalizedLocale);
    final exactMatches = <JurisdictaSpeakerVoice>[];
    final fallbackMatches = <JurisdictaSpeakerVoice>[];
    final genericMatches = <JurisdictaSpeakerVoice>[];

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

      final rawLocale = normalizedVoice['locale'] ?? '';
      final voiceLocale = _normalizeLocaleTag(rawLocale);
      final voiceName = normalizedVoice['name'] ?? rawLocale;
      final speakerVoice = JurisdictaSpeakerVoice(
        id: '${voiceLocale.isEmpty ? 'unknown' : voiceLocale}::$voiceName',
        name: voiceName,
        locale: rawLocale.isEmpty ? locale : rawLocale,
        config: normalizedVoice,
      );

      if (voiceLocale == normalizedLocale) {
        exactMatches.add(speakerVoice);
        continue;
      }

      if (_matchesPreferredVoice(speakerVoice, preferredTags)) {
        fallbackMatches.add(speakerVoice);
        continue;
      }

      if (_isGenericVoiceCandidate(speakerVoice)) {
        genericMatches.add(speakerVoice);
      }
    }

    final preferred = exactMatches.isNotEmpty
        ? exactMatches
        : fallbackMatches.isNotEmpty
            ? fallbackMatches
            : genericMatches;
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
    return voices.first;
  }

  int _voiceRank(JurisdictaSpeakerVoice voice, String targetLocale) {
    final name = voice.name.toLowerCase();
    final locale = _normalizeLocaleTag(voice.locale);
    var score = 0;
    score += _localePreferenceScore(locale, targetLocale);
    score += _namePreferenceScore(name, targetLocale);
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

  int _namePreferenceScore(String name, String targetLocale) {
    final normalizedTarget = _normalizeLocaleTag(targetLocale);
    switch (normalizedTarget) {
      case 'sk-sk':
        if (name.contains('slovak') || name.contains('slovenc')) {
          return 300;
        }
        if (name.contains('czech') ||
            name.contains('cesk') ||
            name.contains('česk')) {
          return 220;
        }
        break;
      case 'cs-cz':
        if (name.contains('czech') ||
            name.contains('cesk') ||
            name.contains('česk')) {
          return 300;
        }
        if (name.contains('slovak') || name.contains('slovenc')) {
          return 220;
        }
        break;
      case 'de-de':
        if (name.contains('german') || name.contains('deutsch')) {
          return 300;
        }
        break;
    }
    if (name.contains('english') ||
        name.contains('en-us') ||
        name.contains('en_gb')) {
      return 40;
    }
    return 0;
  }

  int _localePreferenceScore(String voiceLocale, String targetLocale) {
    final normalizedTarget = _normalizeLocaleTag(targetLocale);
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

  bool _matchesPreferredVoice(
    JurisdictaSpeakerVoice voice,
    List<String> preferredTags,
  ) {
    final locale = _normalizeLocaleTag(voice.locale);
    final localeLanguage = _languagePart(locale);
    final name = voice.name.toLowerCase();

    for (final tag in preferredTags) {
      if (tag.contains('-')) {
        if (locale == tag) {
          return true;
        }
        continue;
      }

      if (localeLanguage == tag) {
        return true;
      }
      if (_voiceNameMatchesLanguage(name, tag)) {
        return true;
      }
    }

    return false;
  }

  bool _isGenericVoiceCandidate(JurisdictaSpeakerVoice voice) {
    final locale = _normalizeLocaleTag(voice.locale);
    if (locale.isNotEmpty) {
      return true;
    }
    final name = voice.name.trim().toLowerCase();
    return name.contains('english') || name.contains('default');
  }

  bool _voiceNameMatchesLanguage(String name, String languageTag) {
    switch (languageTag) {
      case 'sk':
        return name.contains('slovak') || name.contains('slovenc');
      case 'cs':
        return name.contains('czech') ||
            name.contains('cesk') ||
            name.contains('česk');
      case 'de':
        return name.contains('german') || name.contains('deutsch');
      case 'en':
        return name.contains('english');
      default:
        return false;
    }
  }

  List<String> _preferredVoiceTags(String targetLocale) {
    switch (targetLocale) {
      case 'sk-sk':
        return const <String>['sk-sk', 'sk', 'cs-cz', 'cs', 'en-us', 'en'];
      case 'cs-cz':
        return const <String>['cs-cz', 'cs', 'sk-sk', 'sk', 'en-us', 'en'];
      case 'de-de':
        return const <String>['de-de', 'de-at', 'de-ch', 'de', 'en-us', 'en'];
      default:
        return <String>[
          targetLocale,
          _languagePart(targetLocale),
          'en-us',
          'en'
        ];
    }
  }

  List<String> _localeFallbacks(String targetLocale) {
    switch (targetLocale) {
      case 'de-de':
        return const <String>['de-at', 'de-ch', 'en-us'];
      case 'sk-sk':
        return const <String>['sk', 'cs-cz', 'cs', 'en-us'];
      case 'cs-cz':
        return const <String>['cs', 'sk-sk', 'sk', 'en-us'];
      default:
        return const <String>[];
    }
  }

  String _normalizeLocaleTag(String value) {
    return value.trim().replaceAll('_', '-').toLowerCase();
  }

  String _languagePart(String locale) {
    return locale.split('-').first;
  }
}
