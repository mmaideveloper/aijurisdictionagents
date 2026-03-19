import 'dart:convert';

import 'package:audioplayers/audioplayers.dart';
import 'package:flutter/foundation.dart';
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
    final explicitEndpoint = endpoint?.trim();
    if (explicitEndpoint != null && explicitEndpoint.isNotEmpty) {
      return Uri.parse(explicitEndpoint);
    }
    final normalizedRegion = (region ?? '').trim();
    return Uri.parse(
      'https://$normalizedRegion.tts.speech.microsoft.com/cognitiveservices/v1',
    );
  }

  Uri get voicesUri {
    final explicitEndpoint = endpoint?.trim();
    if (explicitEndpoint != null && explicitEndpoint.isNotEmpty) {
      final base = Uri.parse(explicitEndpoint);
      return base.replace(path: '/cognitiveservices/voices/list');
    }
    final normalizedRegion = (region ?? '').trim();
    return Uri.parse(
      'https://$normalizedRegion.tts.speech.microsoft.com/cognitiveservices/voices/list',
    );
  }
}

class AzureSpeechSpeaker implements JurisdictaSpeaker {
  AzureSpeechSpeaker({
    required AzureSpeechConfig config,
    required JurisdictaSpeaker fallbackSpeaker,
    http.Client? httpClient,
    AudioPlayer? audioPlayer,
  }) : _config = config,
       _fallbackSpeaker = fallbackSpeaker,
       _httpClient = httpClient ?? http.Client(),
       _audioPlayer = audioPlayer ?? AudioPlayer();

  final AzureSpeechConfig _config;
  final JurisdictaSpeaker _fallbackSpeaker;
  final http.Client _httpClient;
  final AudioPlayer _audioPlayer;

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
    await _audioPlayer.setReleaseMode(ReleaseMode.stop);
    if (!_config.isConfigured || kIsWeb) {
      return _fallbackSpeaker.initialize();
    }
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
    if (!_config.isConfigured || kIsWeb) {
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
        return _fallbackSpeaker.listVoices(languageCode: languageCode);
      }
      final payload = jsonDecode(response.body);
      if (payload is! List) {
        return _fallbackSpeaker.listVoices(languageCode: languageCode);
      }
      final voices = payload
          .whereType<Map<String, dynamic>>()
          .map(_voiceFromAzureJson)
          .whereType<JurisdictaSpeakerVoice>()
          .where((voice) => _normalizeLocaleTag(voice.locale) == _normalizeLocaleTag(locale))
          .toList(growable: false);
      if (voices.isEmpty) {
        return _fallbackSpeaker.listVoices(languageCode: languageCode);
      }
      _voicesByLocale[locale] = voices;
      _selectedVoiceByLocale[locale] ??= voices.first;
      _selectedVoiceIdByLocale[locale] ??= voices.first.id;
      return voices;
    } catch (_) {
      return _fallbackSpeaker.listVoices(languageCode: languageCode);
    }
  }

  @override
  Future<void> selectVoice({
    required String languageCode,
    required String? voiceId,
  }) async {
    final locale = _ttsLocale(languageCode);
    if (!_config.isConfigured || kIsWeb) {
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
    if (!_config.isConfigured || kIsWeb) {
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
    if (!_config.isConfigured || kIsWeb) {
      return _fallbackSpeaker.speak(text: text, languageCode: languageCode);
    }

    final locale = _ttsLocale(languageCode);
    final voices = await listVoices(languageCode: languageCode);
    final selectedVoice =
        _selectedVoiceByLocale[locale] ?? (voices.isNotEmpty ? voices.first : null);
    if (selectedVoice == null) {
      return _fallbackSpeaker.speak(text: text, languageCode: languageCode);
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
        return _fallbackSpeaker.speak(text: text, languageCode: languageCode);
      }
      await _audioPlayer.stop();
      await _audioPlayer.play(BytesSource(response.bodyBytes));
      await _audioPlayer.onPlayerComplete.first;
      return true;
    } catch (_) {
      return _fallbackSpeaker.speak(text: text, languageCode: languageCode);
    }
  }

  @override
  Future<void> stop() async {
    if (!_config.isConfigured || kIsWeb) {
      await _fallbackSpeaker.stop();
      return;
    }
    await _audioPlayer.stop();
  }

  JurisdictaSpeakerVoice? _voiceFromAzureJson(Map<String, dynamic> raw) {
    final shortName = raw['ShortName']?.toString();
    final locale = raw['Locale']?.toString();
    if (shortName == null || shortName.isEmpty || locale == null || locale.isEmpty) {
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
      },
    );
  }

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
