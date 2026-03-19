import 'package:speech_to_text/speech_recognition_error.dart';
import 'package:speech_to_text/speech_recognition_result.dart';
import 'package:speech_to_text/speech_to_text.dart';

import 'audio/azure_speech_speaker.dart';
import 'audio/jurisdicta_speaker.dart';

typedef JurisdictaSpeakerFactory = JurisdictaSpeaker Function();
typedef AzureJurisdictaSpeakerFactory = JurisdictaSpeaker Function(
  SpeechServiceConfig config,
  JurisdictaSpeaker fallbackSpeaker,
);
typedef JurisdictaSpeechRecognizerFactory = JurisdictaSpeechRecognizer Function(
    SpeechServiceConfig config);

const String _speechModeDefine = String.fromEnvironment(
  'AIJ_SPEECH_MODE',
  defaultValue: 'local',
);
const String _speechProviderDefine = String.fromEnvironment(
  'AIJ_SPEECH_PROVIDER',
  defaultValue: '',
);
const String _azureSpeechKeyDefine = String.fromEnvironment(
  'AIJ_AZURE_SPEECH_KEY',
  defaultValue: '',
);
const String _azureSpeechRegionDefine = String.fromEnvironment(
  'AIJ_AZURE_SPEECH_REGION',
  defaultValue: '',
);
const String _azureSpeechEndpointDefine = String.fromEnvironment(
  'AIJ_AZURE_SPEECH_ENDPOINT',
  defaultValue: '',
);

enum SpeechMode { local, azure }

SpeechMode _parseSpeechMode(String rawValue) {
  switch (rawValue.trim().toLowerCase()) {
    case 'azure':
      return SpeechMode.azure;
    case 'device':
    case 'platform':
    case 'native':
    case 'local':
    default:
      return SpeechMode.local;
  }
}

class SpeechServiceConfig {
  const SpeechServiceConfig({
    required this.mode,
    this.azureKey,
    this.azureRegion,
    this.azureEndpoint,
    this.listenFor = const Duration(minutes: 30),
    this.pauseFor = const Duration(milliseconds: 1500),
    this.autoSendDelay = const Duration(seconds: 2),
    this.resumeListeningDelay = const Duration(milliseconds: 150),
  });

  factory SpeechServiceConfig.fromEnvironment() {
    final requestedMode = _speechModeDefine.trim().isNotEmpty
        ? _speechModeDefine
        : _speechProviderDefine;
    return SpeechServiceConfig(
      mode: _parseSpeechMode(requestedMode),
      azureKey: _emptyToNull(_azureSpeechKeyDefine),
      azureRegion: _emptyToNull(_azureSpeechRegionDefine),
      azureEndpoint: _emptyToNull(_azureSpeechEndpointDefine),
    );
  }

  final SpeechMode mode;
  final String? azureKey;
  final String? azureRegion;
  final String? azureEndpoint;
  final Duration listenFor;
  final Duration pauseFor;
  final Duration autoSendDelay;
  final Duration resumeListeningDelay;

  bool get hasAzureSpeechConfig {
    return (azureKey != null && azureKey!.isNotEmpty) &&
        ((azureRegion != null && azureRegion!.isNotEmpty) ||
            (azureEndpoint != null && azureEndpoint!.isNotEmpty));
  }

  static String? _emptyToNull(String value) {
    final normalized = value.trim();
    return normalized.isEmpty ? null : normalized;
  }
}

abstract class JurisdictaSpeechRecognizer {
  Future<bool> initialize({
    required void Function(SpeechRecognitionError error) onError,
    required void Function(String status) onStatus,
  });

  Future<void> listen({
    required void Function(SpeechRecognitionResult result) onResult,
    required String localeId,
    Duration? listenFor,
    Duration? pauseFor,
    bool partialResults = true,
    bool cancelOnError = true,
    ListenMode listenMode = ListenMode.dictation,
  });

  Future<void> stop();
}

abstract class JurisdictaSpeechService {
  SpeechServiceConfig get config;
  JurisdictaSpeaker get speaker;
  JurisdictaSpeechRecognizer get recognizer;
  String get modeLabel;
  String get runtimeModeLabel;
}

class SpeechServiceFactory {
  const SpeechServiceFactory({
    this.speakerFactory = createJurisdictaSpeaker,
    this.azureSpeakerFactory = _defaultAzureSpeakerFactory,
    this.recognizerFactory = _defaultSpeechRecognizerFactory,
  });

  final JurisdictaSpeakerFactory speakerFactory;
  final AzureJurisdictaSpeakerFactory azureSpeakerFactory;
  final JurisdictaSpeechRecognizerFactory recognizerFactory;

  JurisdictaSpeechService create({SpeechServiceConfig? config}) {
    final resolvedConfig = config ?? SpeechServiceConfig.fromEnvironment();
    switch (resolvedConfig.mode) {
      case SpeechMode.azure:
        return AzureSpeechService(
          config: resolvedConfig,
          recognizerFactory: recognizerFactory,
          speakerFactory: speakerFactory,
          azureSpeakerFactory: azureSpeakerFactory,
        );
      case SpeechMode.local:
        return LocalSpeechService(
          config: resolvedConfig,
          recognizerFactory: recognizerFactory,
          speakerFactory: speakerFactory,
        );
    }
  }
}

class LocalSpeechService implements JurisdictaSpeechService {
  LocalSpeechService({
    required this.config,
    JurisdictaSpeakerFactory speakerFactory = createJurisdictaSpeaker,
    JurisdictaSpeechRecognizerFactory recognizerFactory =
        _defaultSpeechRecognizerFactory,
  })  : speaker = speakerFactory(),
        recognizer = recognizerFactory(config);

  @override
  final SpeechServiceConfig config;

  @override
  final JurisdictaSpeechRecognizer recognizer;

  @override
  final JurisdictaSpeaker speaker;

  @override
  String get modeLabel => 'local';

  @override
  String get runtimeModeLabel => 'device-speech';
}

class AzureSpeechService implements JurisdictaSpeechService {
  AzureSpeechService({
    required this.config,
    JurisdictaSpeechRecognizerFactory recognizerFactory =
        _defaultSpeechRecognizerFactory,
    JurisdictaSpeakerFactory speakerFactory = createJurisdictaSpeaker,
    AzureJurisdictaSpeakerFactory azureSpeakerFactory =
        _defaultAzureSpeakerFactory,
  })  : recognizer = recognizerFactory(config),
        speaker = azureSpeakerFactory(config, speakerFactory());

  @override
  final SpeechServiceConfig config;

  @override
  final JurisdictaSpeechRecognizer recognizer;

  @override
  final JurisdictaSpeaker speaker;

  @override
  String get modeLabel => 'azure';

  @override
  String get runtimeModeLabel => config.hasAzureSpeechConfig
      ? 'azure-tts-local-stt'
      : 'azure-fallback-local';
}

class PlatformSpeechRecognizer implements JurisdictaSpeechRecognizer {
  PlatformSpeechRecognizer({required this.config});

  final SpeechServiceConfig config;
  final SpeechToText _speechToText = SpeechToText();

  @override
  Future<bool> initialize({
    required void Function(SpeechRecognitionError error) onError,
    required void Function(String status) onStatus,
  }) {
    return _speechToText.initialize(onError: onError, onStatus: onStatus);
  }

  @override
  Future<void> listen({
    required void Function(SpeechRecognitionResult result) onResult,
    required String localeId,
    Duration? listenFor,
    Duration? pauseFor,
    bool partialResults = true,
    bool cancelOnError = true,
    ListenMode listenMode = ListenMode.dictation,
  }) {
    return _speechToText.listen(
      onResult: onResult,
      localeId: localeId,
      listenFor: listenFor ?? config.listenFor,
      pauseFor: pauseFor ?? config.pauseFor,
      partialResults: partialResults,
      cancelOnError: cancelOnError,
      listenMode: listenMode,
    );
  }

  @override
  Future<void> stop() {
    return _speechToText.stop();
  }
}

JurisdictaSpeechRecognizer _defaultSpeechRecognizerFactory(
  SpeechServiceConfig config,
) {
  return PlatformSpeechRecognizer(config: config);
}

JurisdictaSpeaker _defaultAzureSpeakerFactory(
  SpeechServiceConfig config,
  JurisdictaSpeaker fallbackSpeaker,
) {
  return AzureSpeechSpeaker(
    config: AzureSpeechConfig(
      key: config.azureKey ?? '',
      region: config.azureRegion,
      endpoint: config.azureEndpoint,
    ),
    fallbackSpeaker: fallbackSpeaker,
  );
}
