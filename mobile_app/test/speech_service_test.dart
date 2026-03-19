import 'package:ai_jurisdiction_mobile/audio/azure_speech_speaker.dart';
import 'package:ai_jurisdiction_mobile/audio/jurisdicta_speaker.dart';
import 'package:ai_jurisdiction_mobile/speech_service.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:speech_to_text/speech_to_text.dart';

void main() {
  group('SpeechServiceConfig', () {
    test('defaults to local mode with tuned timing values', () {
      final config = SpeechServiceConfig.fromEnvironment();

      expect(config.mode, SpeechMode.local);
      expect(config.pauseFor, const Duration(milliseconds: 1500));
      expect(config.autoSendDelay, const Duration(seconds: 2));
      expect(config.resumeListeningDelay, const Duration(milliseconds: 150));
    });
  });

  group('AzureSpeechConfig', () {
    test('builds regional TTS and voices endpoints', () {
      const config = AzureSpeechConfig(key: 'key', region: 'westeurope');

      expect(
        config.ttsUri.toString(),
        'https://westeurope.tts.speech.microsoft.com/cognitiveservices/v1',
      );
      expect(
        config.voicesUri.toString(),
        'https://westeurope.tts.speech.microsoft.com/cognitiveservices/voices/list',
      );
    });
  });

  group('SpeechServiceFactory', () {
    final factory = SpeechServiceFactory(
      speakerFactory: _FakeSpeaker.new,
      azureSpeakerFactory: (config, fallbackSpeaker) => fallbackSpeaker,
      recognizerFactory: _FakeRecognizer.new,
    );

    test('creates local service when local mode is requested', () {
      final service = factory.create(
        config: const SpeechServiceConfig(mode: SpeechMode.local),
      );

      expect(service.modeLabel, 'local');
      expect(service.runtimeModeLabel, 'device-speech');
    });

    test('creates azure service when azure mode is requested', () {
      final service = factory.create(
        config: const SpeechServiceConfig(mode: SpeechMode.azure),
      );

      expect(service.modeLabel, 'azure');
      expect(service.runtimeModeLabel, 'azure-fallback-local');
    });

    test('marks azure runtime when azure credentials are configured', () {
      final service = factory.create(
        config: const SpeechServiceConfig(
          mode: SpeechMode.azure,
          azureKey: 'key',
          azureRegion: 'westeurope',
        ),
      );

      expect(service.runtimeModeLabel, 'azure-tts-local-stt');
    });
  });
}

class _FakeRecognizer implements JurisdictaSpeechRecognizer {
  _FakeRecognizer(SpeechServiceConfig config);

  @override
  Future<bool> initialize({required onError, required onStatus}) async => true;

  @override
  Future<void> listen({
    required onResult,
    required String localeId,
    Duration? listenFor,
    Duration? pauseFor,
    bool partialResults = true,
    bool cancelOnError = true,
    listenMode = ListenMode.dictation,
  }) async {}

  @override
  Future<void> stop() async {}
}

class _FakeSpeaker implements JurisdictaSpeaker {
  @override
  Future<bool> initialize() async => true;

  @override
  Future<List<JurisdictaSpeakerVoice>> listVoices({
    required String languageCode,
  }) async =>
      const <JurisdictaSpeakerVoice>[];

  @override
  Future<void> selectVoice({
    required String languageCode,
    required String? voiceId,
  }) async {}

  @override
  String? selectedVoiceIdFor({required String languageCode}) => null;

  @override
  Future<bool> speak({
    required String text,
    required String languageCode,
  }) async =>
      true;

  @override
  Future<void> stop() async {}
}
