import 'dart:convert';

import 'package:audioplayers/audioplayers.dart';
import 'package:http/http.dart' as http;

import 'jurisdicta_speaker.dart';

class AzureSpeechConfig {
  const AzureSpeechConfig({
    required this.key,
    this.region,
    this.endpoint,
  });

  final String key;
  final String? region;
  final String? endpoint;

  bool get isConfigured {
    return key.trim().isNotEmpty &&
        ((region != null && region!.trim().isNotEmpty) ||
            (endpoint != null && endpoint!.trim().isNotEmpty));
  }

  Uri get ttsUri {
    return _baseEndpoint('cognitiveservices/v1');
  }

  Uri get voicesUri {
    return _baseEndpoint('cognitiveservices/voices/list');
  }

  Uri _baseEndpoint(String pathSuffix) {
    final explicitEndpoint = endpoint?.trim();
    if (explicitEndpoint != null && explicitEndpoint.isNotEmpty) {
      final parsed = Uri.parse(explicitEndpoint);
      final normalizedPath = parsed.path.trim();
      if (normalizedPath.isEmpty || normalizedPath == '/') {
        return parsed.replace(path: '/$pathSuffix');
      }
      if (normalizedPath.endsWith('/$pathSuffix')) {
        return parsed;
      }
      if (normalizedPath.endsWith('/cognitiveservices/v1') &&
          pathSuffix == 'cognitiveservices/voices/list') {
        return parsed.replace(path: '/cognitiveservices/voices/list');
      }
      return parsed.replace(
        path: normalizedPath.startsWith('/')
            ? normalizedPath
            : '/$normalizedPath',
      );
    }
    final normalizedRegion = (region ?? '').trim();
    return Uri.parse(
      'https://$normalizedRegion.tts.speech.microsoft.com/$pathSuffix',
    );
  }
}

class AzureSpeechSpeaker implements JurisdictaSpeaker {
  AzureSpeechSpeaker({
    required AzureSpeechConfig config,
    required JurisdictaSpeaker fallbackSpeaker,
    http.Client? httpClient,
    AudioPlayer? audioPlayer,
  })  : _config = config,
        _fallbackSpeaker = fallbackSpeaker,
        _httpClient = httpClient ?? http.Client(),
        _audioPlayer = audioPlayer;

  final AzureSpeechConfig _config;
  final JurisdictaSpeaker _fallbackSpeaker;
  final http.Client _httpClient;
  AudioPlayer? _audioPlayer;

  bool _initialized = false;
  final Map<String, List<JurisdictaSpeakerVoice>> _voicesByLocale =
      <String, List<JurisdictaSpeakerVoice>>{};
  final Map<String, String?> _selectedVoiceIdByLocale = <String, String?>{};
  final Map<String, JurisdictaSpeakerVoice?> _selectedVoiceByLocale =
      <String, JurisdictaSpeakerVoice?>{};

  @override
  Future<bool> initialize() async {
    if (_initialized) {
      return true;
    }
    _initialized = true;
    if (!_config.isConfigured) {
      return _fallbackSpeaker.initialize();
    }
    await _player.setReleaseMode(ReleaseMode.stop);
    return true;
  }

  @override
  Future<List<JurisdictaSpeakerVoice>> listVoices({
    required String languageCode,
  }) async {
    final locale = _ttsLocale(languageCode);
    final cached = _voicesByLocale[locale];
    if (cached != null && cached.isNotEmpty) {
      return cached;
    }
    if (!_config.isConfigured) {
      return _fallbackSpeaker.listVoices(languageCode: languageCode);
    }

    try {
      final response = await _httpClient.get(
        _config.voicesUri,
        headers: <String, String>{
          'Ocp-Apim-Subscription-Key': _config.key,
        },
      );
      if (response.statusCode < 200 || response.statusCode >= 300) {
        return const <JurisdictaSpeakerVoice>[];
      }
      final payload = jsonDecode(response.body);
      if (payload is! List) {
        return const <JurisdictaSpeakerVoice>[];
      }
      final voices = payload
          .whereType<Map<String, dynamic>>()
          .map(_voiceFromAzureJson)
          .whereType<JurisdictaSpeakerVoice>()
          .where((voice) => _voiceMatchesLocale(voice, locale))
          .toList(growable: false)
        ..sort(
          (left, right) => left.name.toLowerCase().compareTo(
                right.name.toLowerCase(),
              ),
        );
      if (voices.isEmpty) {
        return const <JurisdictaSpeakerVoice>[];
      }
      _voicesByLocale[locale] = voices;
      _selectedVoiceByLocale[locale] ??= voices.first;
      _selectedVoiceIdByLocale[locale] ??= voices.first.id;
      return voices;
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
    if (!_config.isConfigured) {
      return _fallbackSpeaker.selectVoice(
        languageCode: languageCode,
        voiceId: voiceId,
      );
    }
    final voices = await listVoices(languageCode: languageCode);
    if (voiceId == null || voiceId.isEmpty) {
      final fallbackVoice = voices.isNotEmpty ? voices.first : null;
      _selectedVoiceByLocale[locale] = fallbackVoice;
      _selectedVoiceIdByLocale[locale] = fallbackVoice?.id;
      return;
    }
    final selectedVoice = voices.cast<JurisdictaSpeakerVoice?>().firstWhere(
          (voice) => voice?.id == voiceId,
          orElse: () => null,
        );
    if (selectedVoice != null) {
      _selectedVoiceByLocale[locale] = selectedVoice;
      _selectedVoiceIdByLocale[locale] = selectedVoice.id;
    }
  }

  @override
  String? selectedVoiceIdFor({
    required String languageCode,
  }) {
    if (!_config.isConfigured) {
      return _fallbackSpeaker.selectedVoiceIdFor(languageCode: languageCode);
    }
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
    if (!_config.isConfigured) {
      return _fallbackSpeaker.speak(text: text, languageCode: languageCode);
    }

    final locale = _ttsLocale(languageCode);
    final voices = await listVoices(languageCode: languageCode);
    final selectedVoice = _selectedVoiceByLocale[locale] ??
        (voices.isNotEmpty ? voices.first : null);
    if (selectedVoice == null) {
      return false;
    }

    try {
      final response = await _httpClient.post(
        _config.ttsUri,
        headers: <String, String>{
          'Ocp-Apim-Subscription-Key': _config.key,
          'Content-Type': 'application/ssml+xml',
          'X-Microsoft-OutputFormat': 'audio-24khz-48kbitrate-mono-mp3',
          'User-Agent': 'ai-jurisdiction-mobile',
        },
        body: _buildSsml(
          text: message,
          languageCode: languageCode,
          voiceName: selectedVoice.config['shortName'] ?? selectedVoice.name,
        ),
      );
      if (response.statusCode < 200 || response.statusCode >= 300) {
        return false;
      }
      await _player.stop();
      await _player.play(BytesSource(response.bodyBytes));
      await _player.onPlayerComplete.first;
      return true;
    } catch (_) {
      return false;
    }
  }

  @override
  Future<void> stop() async {
    if (!_config.isConfigured) {
      await _fallbackSpeaker.stop();
      return;
    }
    await _player.stop();
  }

  JurisdictaSpeakerVoice? _voiceFromAzureJson(Map<String, dynamic> raw) {
    final shortName = raw['ShortName']?.toString();
    final locale = raw['Locale']?.toString();
    if (shortName == null ||
        shortName.isEmpty ||
        locale == null ||
        locale.isEmpty) {
      return null;
    }
    final displayName = raw['DisplayName']?.toString() ?? shortName;
    return JurisdictaSpeakerVoice(
      id: shortName,
      name: displayName,
      locale: locale,
      config: <String, String>{
        'shortName': shortName,
        'locale': locale,
        'name': displayName,
        'secondaryLocales': _encodeSecondaryLocales(raw['SecondaryLocaleList']),
      },
    );
  }

  bool _voiceMatchesLocale(JurisdictaSpeakerVoice voice, String locale) {
    final normalizedLocale = _normalizeLocaleTag(locale);
    final voiceLocale = _normalizeLocaleTag(voice.locale);
    return voiceLocale == normalizedLocale;
  }

  String _encodeSecondaryLocales(dynamic rawValue) {
    if (rawValue is! List) {
      return '';
    }
    return rawValue
        .map((item) => item?.toString().trim() ?? '')
        .where((item) => item.isNotEmpty)
        .join(',');
  }

  AudioPlayer get _player => _audioPlayer ??= AudioPlayer();

  String _buildSsml({
    required String text,
    required String languageCode,
    required String voiceName,
  }) {
    final rate = _prosodyRate(languageCode);
    final escapedText = const HtmlEscape(HtmlEscapeMode.element).convert(text);
    final locale = _ttsLocale(languageCode);
    return '<speak version="1.0" xml:lang="$locale"><voice name="$voiceName"><prosody rate="$rate">$escapedText</prosody></voice></speak>';
  }

  String _prosodyRate(String languageCode) {
    switch (languageCode.trim().toUpperCase()) {
      case 'SK':
      case 'CS':
        return '+8%';
      case 'DE':
      case 'GE':
        return '+6%';
      case 'EN':
      default:
        return '+4%';
    }
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

  String _normalizeLocaleTag(String value) {
    return value.trim().replaceAll('_', '-').toLowerCase();
  }
}
