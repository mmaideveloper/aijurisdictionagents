import 'package:flutter_tts/flutter_tts.dart';

abstract class JurisdictaSpeaker {
  Future<bool> initialize();
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
      await _tts.stop();
      await _tts.setLanguage(_ttsLocale(languageCode));
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
}
