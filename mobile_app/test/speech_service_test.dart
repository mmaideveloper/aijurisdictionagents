import 'package:ai_jurisdiction_mobile/audio/azure_speech_speaker.dart';
import 'package:ai_jurisdiction_mobile/speech_service.dart';
import 'package:flutter_test/flutter_test.dart';

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
    const factory = SpeechServiceFactory();

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
