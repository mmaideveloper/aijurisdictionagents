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
  static const int _voiceRetryAttempts = 4;
  bool _initialized = false;
  bool _available = true;
  final Map<String, List<JurisdictaSpeakerVoice>> _voicesByLocale =
      <String, List<JurisdictaSpeakerVoice>>{};
  final Map<String, String?> _selectedVoiceIdByLocale = <String, String?>{};
  final Map<String, JurisdictaSpeakerVoice?> _resolvedVoiceByLocale =
      <String, JurisdictaSpeakerVoice?>{};

  @override
  Future<bool> initialize() async {
    if (_initialized) {
      return _available;
    }
    try {
      await _tts.awaitSpeakCompletion(true);
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
        final defaultVoice =
            resolved.isNotEmpty ? _preferDefaultVoice(resolved, locale) : null;
        _selectedVoiceIdByLocale[locale] = defaultVoice?.id;
        _resolvedVoiceByLocale[locale] = defaultVoice;
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
      final fallbackVoice =
          voices.isNotEmpty ? _preferDefaultVoice(voices, locale) : null;
      _selectedVoiceIdByLocale[locale] = fallbackVoice?.id;
      _resolvedVoiceByLocale[locale] = fallbackVoice;
      return;
    }

    final selectedVoice = voices.cast<JurisdictaSpeakerVoice?>().firstWhere(
          (voice) => voice?.id == voiceId,
          orElse: () => null,
        );
    if (selectedVoice != null) {
      _selectedVoiceIdByLocale[locale] = voiceId;
      _resolvedVoiceByLocale[locale] = selectedVoice;
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
      var selectedVoice = _resolvedVoiceByLocale[locale];
      if (selectedVoice == null) {
        final voices = await listVoices(languageCode: languageCode);
        final selectedVoiceId = _selectedVoiceIdByLocale[locale];
        selectedVoice = voices.cast<JurisdictaSpeakerVoice?>().firstWhere(
              (item) => item?.id == selectedVoiceId,
              orElse: () =>
                  voices.isNotEmpty ? _preferDefaultVoice(voices, locale) : null,
            );
        _resolvedVoiceByLocale[locale] = selectedVoice;
      }
      await _tts.stop();
      await _tts.setSpeechRate(_speechRate(languageCode));
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
          Duration(milliseconds: 120 * (attempt + 1)),
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

  double _speechRate(String languageCode) {
    switch (languageCode.trim().toUpperCase()) {
      case 'SK':
      case 'CS':
        return 0.92;
      case 'DE':
      case 'GE':
        return 0.95;
      case 'EN':
      default:
        return 0.98;
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
    String locale,
  ) {
    final normalizedLocale = _normalizeLocaleTag(locale);
    if (normalizedLocale == 'sk-sk') {
      for (final voice in voices) {
        if (_normalizeLocaleTag(voice.locale) == 'sk-sk') {
          return voice;
        }
      }
    }
    return voices.first;
  }

  int _voiceRank(JurisdictaSpeakerVoice voice, String targetLocale) {
    final name = voice.name.toLowerCase();
    final locale = _normalizeLocaleTag(voice.locale);
    final exactLocaleScore = _localePreferenceScore(locale, targetLocale);
    var score = exactLocaleScore * 100;

    if (name.contains('neural')) {
      score += 40;
    }
    if (name.contains('premium')) {
      score += 15;
    }
    if (name.contains('enhanced')) {
      score += 10;
    }
    if (name.contains('male') || name.contains('female')) {
      score += 5;
    }
    return score;
  }

  String _normalizeLocaleTag(String value) {
    return value.trim().replaceAll('_', '-').toLowerCase();
  }

  List<String> _preferredVoiceTags(String normalizedLocale) {
    switch (normalizedLocale) {
      case 'sk-sk':
        return const <String>['slovak', 'sk-sk', 'cs-cz', 'czech', 'en-us'];
      case 'cs-cz':
        return const <String>['czech', 'cs-cz', 'sk-sk', 'slovak', 'en-us'];
      case 'de-de':
        return const <String>[
          'de-de',
          'de-at',
          'de-ch',
          'german',
          'en-us',
        ];
      case 'en-us':
      default:
        return const <String>['en-us', 'english'];
    }
  }

  bool _matchesPreferredVoice(
    JurisdictaSpeakerVoice voice,
    List<String> preferredTags,
  ) {
    final locale = _normalizeLocaleTag(voice.locale);
    final name = voice.name.toLowerCase();
    for (final tag in preferredTags) {
      if (locale == tag || locale.startsWith('$tag-')) {
        return true;
      }
      if (_voiceNameMatchesLanguage(name, tag)) {
        return true;
      }
    }
    return false;
  }

  int _localePreferenceScore(String voiceLocale, String targetLocale) {
    final normalizedTarget = _normalizeLocaleTag(targetLocale);
    if (voiceLocale == normalizedTarget) {
      return 5;
    }

    final fallbacks = <String>{
      ..._preferredVoiceTags(normalizedTarget).where((tag) => tag.contains('-')),
    }.toList(growable: false);
    final fallbackIndex = fallbacks.indexOf(voiceLocale);
    if (fallbackIndex >= 0) {
      return 4 - fallbackIndex;
    }

    if (voiceLocale.startsWith('${normalizedTarget.split('-').first}-')) {
      return 2;
    }
    if (voiceLocale.startsWith('en-')) {
      return 1;
    }
    return 0;
  }

  bool _isGenericVoiceCandidate(JurisdictaSpeakerVoice voice) {
    final locale = _normalizeLocaleTag(voice.locale);
    if (locale.startsWith('en-')) {
      return true;
    }
    final name = voice.name.trim().toLowerCase();
    return name.contains('neural') || name.contains('voice');
  }

  bool _voiceNameMatchesLanguage(String name, String languageTag) {
    switch (languageTag) {
      case 'slovak':
      case 'sk-sk':
        return name.contains('slovak') || name.contains('slovensky');
      case 'czech':
      case 'cs-cz':
        return name.contains('czech') || name.contains('cesky');
      case 'german':
      case 'de-de':
      case 'de-at':
      case 'de-ch':
        return name.contains('german') || name.contains('deutsch');
      case 'english':
      case 'en-us':
        return name.contains('english');
      default:
        return name.contains(languageTag);
    }
  }
}
