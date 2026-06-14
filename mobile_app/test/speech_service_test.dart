import 'package:ai_jurisdiction_mobile/audio/azure_speech_speaker.dart';
import 'package:ai_jurisdiction_mobile/audio/jurisdicta_speaker.dart';
import 'package:ai_jurisdiction_mobile/speech_service.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:speech_to_text/speech_to_text.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('SpeechServiceConfig', () {
    test('defaults to local mode with tuned timing values', () {
      final config = SpeechServiceConfig.fromEnvironment();

      expect(config.mode, SpeechMode.local);
      expect(config.pauseFor, const Duration(minutes: 10));
      expect(config.autoSendDelay, const Duration(seconds: 2));
      expect(config.resumeListeningDelay, const Duration(milliseconds: 150));
      expect(config.localSttModel, 'whisper-small-multilingual');
      expect(config.localTtsModel, 'piper-sk_SK-katarina-medium');
      expect(config.consentGiven, isFalse);
      expect(config.storeAudioEnabled, isFalse);
      expect(config.redactSensitiveEntitiesBeforeSend, isTrue);
    });

    test('copies voice compliance flags for runtime consent', () {
      final config = const SpeechServiceConfig(mode: SpeechMode.azure).copyWith(
        consentGiven: true,
        storeAudioEnabled: false,
        redactSensitiveEntitiesBeforeSend: true,
      );

      expect(config.consentGiven, isTrue);
      expect(config.complianceFlags.toLogContext(), <String, Object?>{
        'consent_given': true,
        'store_audio_enabled': false,
        'redact_sensitive_entities_before_send': true,
      });
    });
  });

  group('JurisdictaSpeechRecognitionError', () {
    test('classifies browser no-speech as soft no-input timeout', () {
      const error = JurisdictaSpeechRecognitionError(
        errorMsg: 'no-speech',
        permanent: false,
      );

      expect(error.isNoSpeechDetected, isTrue);
    });

    test('does not classify permission errors as no-input timeout', () {
      const error = JurisdictaSpeechRecognitionError(
        errorMsg: 'not-allowed',
        permanent: true,
      );

      expect(error.isNoSpeechDetected, isFalse);
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

    test('accepts base TTS endpoint without path', () {
      const config = AzureSpeechConfig(
        key: 'key',
        endpoint: 'https://eastus2.tts.speech.microsoft.com',
      );

      expect(
        config.ttsUri.toString(),
        'https://eastus2.tts.speech.microsoft.com/cognitiveservices/v1',
      );
      expect(
        config.voicesUri.toString(),
        'https://eastus2.tts.speech.microsoft.com/cognitiveservices/voices/list',
      );
    });
  });

  group('AzureSpeechSpeaker', () {
    test('loads Azure voices instead of local fallback voices', () async {
      final fallbackSpeaker = _TrackingSpeaker();
      final speaker = AzureSpeechSpeaker(
        config: const AzureSpeechConfig(
          key: 'key',
          endpoint: 'https://eastus2.tts.speech.microsoft.com',
        ),
        fallbackSpeaker: fallbackSpeaker,
        httpClient: _FakeHttpClient(
          (request) async => http.Response(
            '''
[
  {"ShortName":"sk-SK-ViktoriaNeural","Locale":"sk-SK","DisplayName":"Viktoria"},
  {"ShortName":"en-US-AvaMultilingualNeural","Locale":"en-US","DisplayName":"Ava Multilingual","SecondaryLocaleList":["sk-SK","de-DE"]}
]
''',
            200,
          ),
        ),
      );

      final voices = await speaker.listVoices(languageCode: 'SK');

      expect(voices.map((voice) => voice.id), <String>[
        'sk-SK-ViktoriaNeural',
      ]);
      expect(fallbackSpeaker.listVoicesCalls, 0);
    });

    test('does not replace Azure voice picker with local voices on failure',
        () async {
      final fallbackSpeaker = _TrackingSpeaker();
      final speaker = AzureSpeechSpeaker(
        config: const AzureSpeechConfig(
          key: 'key',
          endpoint: 'https://eastus2.tts.speech.microsoft.com',
        ),
        fallbackSpeaker: fallbackSpeaker,
        httpClient: _FakeHttpClient(
          (request) async => http.Response('server error', 500),
        ),
      );

      final voices = await speaker.listVoices(languageCode: 'SK');

      expect(voices, isEmpty);
      expect(fallbackSpeaker.listVoicesCalls, 0);
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
      expect(service.config.interactionType, SpeechInteractionType.message);
    });

    test('preserves conversation interaction type when requested', () {
      final service = factory.create(
        config: const SpeechServiceConfig(
          mode: SpeechMode.local,
          interactionType: SpeechInteractionType.conversation,
        ),
      );

      expect(service.modeLabel, 'local');
      expect(
        service.config.interactionType,
        SpeechInteractionType.conversation,
      );
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

      expect(service.runtimeModeLabel, 'azure-stt-tts');
    });

    test('marks mixed runtime when only azure TTS is configured', () {
      final service = factory.create(
        config: const SpeechServiceConfig(
          mode: SpeechMode.azure,
          azureKey: 'key',
          azureTtsEndpoint: 'https://eastus2.tts.speech.microsoft.com',
        ),
      );

      expect(service.runtimeModeLabel, 'azure-tts-local-stt');
    });

    test('marks mixed runtime when only azure STT is configured', () {
      final service = factory.create(
        config: const SpeechServiceConfig(
          mode: SpeechMode.azure,
          azureKey: 'key',
          azureSttEndpoint: 'https://eastus2.stt.speech.microsoft.com',
        ),
      );

      expect(service.runtimeModeLabel, 'local-tts-azure-stt');
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

class _TrackingSpeaker implements JurisdictaSpeaker {
  int listVoicesCalls = 0;

  @override
  Future<bool> initialize() async => true;

  @override
  Future<List<JurisdictaSpeakerVoice>> listVoices({
    required String languageCode,
  }) async {
    listVoicesCalls += 1;
    return const <JurisdictaSpeakerVoice>[
      JurisdictaSpeakerVoice(
        id: 'local::voice',
        name: 'Local Voice',
        locale: 'sk-SK',
        config: <String, String>{},
      ),
    ];
  }

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

class _FakeHttpClient extends http.BaseClient {
  _FakeHttpClient(this._handler);

  final Future<http.Response> Function(http.BaseRequest request) _handler;

  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) async {
    final response = await _handler(request);
    return http.StreamedResponse(
      Stream<List<int>>.value(response.bodyBytes),
      response.statusCode,
      headers: response.headers,
      request: request,
      reasonPhrase: response.reasonPhrase,
    );
  }
}
