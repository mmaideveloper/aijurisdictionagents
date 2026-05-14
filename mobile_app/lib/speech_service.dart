import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:record/record.dart';
import 'package:speech_to_text/speech_recognition_error.dart'
    as platform_speech;
import 'package:speech_to_text/speech_recognition_result.dart'
    as platform_speech;
import 'package:speech_to_text/speech_to_text.dart';

import 'audio/azure_speech_speaker.dart';
import 'audio/jurisdicta_speaker.dart';

typedef JurisdictaSpeakerFactory = JurisdictaSpeaker Function();
typedef AzureJurisdictaSpeakerFactory = JurisdictaSpeaker Function(
  SpeechServiceConfig config,
  JurisdictaSpeaker fallbackSpeaker,
);
typedef JurisdictaSpeechRecognizerFactory = JurisdictaSpeechRecognizer Function(
  SpeechServiceConfig config,
);

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
const String _azureSpeechTtsEndpointDefine = String.fromEnvironment(
  'AIJ_AZURE_SPEECH_TTS_ENDPOINT',
  defaultValue: '',
);
const String _azureSpeechSttEndpointDefine = String.fromEnvironment(
  'AIJ_AZURE_SPEECH_STT_ENDPOINT',
  defaultValue: '',
);
const String _localSttModelDefine = String.fromEnvironment(
  'AIJ_LOCAL_STT_MODEL',
  defaultValue: 'whisper-small-multilingual',
);
const String _localTtsModelDefine = String.fromEnvironment(
  'AIJ_LOCAL_TTS_MODEL',
  defaultValue: 'piper-sk_SK-katarina-medium',
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

class JurisdictaSpeechRecognitionResult {
  const JurisdictaSpeechRecognitionResult({
    required this.recognizedWords,
    required this.finalResult,
  });

  final String recognizedWords;
  final bool finalResult;
}

class JurisdictaSpeechRecognitionError {
  const JurisdictaSpeechRecognitionError({
    required this.errorMsg,
    required this.permanent,
  });

  final String errorMsg;
  final bool permanent;
}

class SpeechServiceConfig {
  const SpeechServiceConfig({
    required this.mode,
    this.azureKey,
    this.azureRegion,
    this.azureEndpoint,
    this.azureTtsEndpoint,
    this.azureSttEndpoint,
    this.localSttModel = 'whisper-small-multilingual',
    this.localTtsModel = 'piper-sk_SK-katarina-medium',
    this.listenFor = const Duration(minutes: 30),
    this.pauseFor = const Duration(seconds: 5),
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
      azureTtsEndpoint: _emptyToNull(_azureSpeechTtsEndpointDefine),
      azureSttEndpoint: _emptyToNull(_azureSpeechSttEndpointDefine),
      localSttModel: _localSttModelDefine.trim().isEmpty
          ? 'whisper-small-multilingual'
          : _localSttModelDefine.trim(),
      localTtsModel: _localTtsModelDefine.trim().isEmpty
          ? 'piper-sk_SK-katarina-medium'
          : _localTtsModelDefine.trim(),
    );
  }

  final SpeechMode mode;
  final String? azureKey;
  final String? azureRegion;
  final String? azureEndpoint;
  final String? azureTtsEndpoint;
  final String? azureSttEndpoint;
  final String localSttModel;
  final String localTtsModel;
  final Duration listenFor;
  final Duration pauseFor;
  final Duration autoSendDelay;
  final Duration resumeListeningDelay;

  bool get hasAzureTtsConfig {
    return (azureKey != null && azureKey!.isNotEmpty) &&
        ((azureTtsEndpoint != null && azureTtsEndpoint!.isNotEmpty) ||
            (azureEndpoint != null && azureEndpoint!.isNotEmpty) ||
            (azureRegion != null && azureRegion!.isNotEmpty));
  }

  bool get hasAzureSttConfig {
    return (azureKey != null && azureKey!.isNotEmpty) &&
        ((azureSttEndpoint != null && azureSttEndpoint!.isNotEmpty) ||
            (azureRegion != null && azureRegion!.isNotEmpty));
  }

  bool get hasAzureSpeechConfig {
    return hasAzureTtsConfig || hasAzureSttConfig;
  }

  static String? _emptyToNull(String value) {
    final normalized = value.trim();
    return normalized.isEmpty ? null : normalized;
  }
}

abstract class JurisdictaSpeechRecognizer {
  Future<bool> initialize({
    required void Function(JurisdictaSpeechRecognitionError error) onError,
    required void Function(String status) onStatus,
  });

  Future<void> listen({
    required void Function(JurisdictaSpeechRecognitionResult result) onResult,
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
  String get runtimeModeLabel {
    if (config.hasAzureTtsConfig && config.hasAzureSttConfig) {
      return 'azure-stt-tts';
    }
    if (config.hasAzureTtsConfig) {
      return 'azure-tts-local-stt';
    }
    if (config.hasAzureSttConfig) {
      return 'local-tts-azure-stt';
    }
    return 'azure-fallback-local';
  }
}

class PlatformSpeechRecognizer implements JurisdictaSpeechRecognizer {
  PlatformSpeechRecognizer({required this.config});

  final SpeechServiceConfig config;
  final SpeechToText _speechToText = SpeechToText();

  @override
  Future<bool> initialize({
    required void Function(JurisdictaSpeechRecognitionError error) onError,
    required void Function(String status) onStatus,
  }) {
    return _speechToText.initialize(
      onError: (platform_speech.SpeechRecognitionError error) {
        onError(
          JurisdictaSpeechRecognitionError(
            errorMsg: error.errorMsg,
            permanent: error.permanent,
          ),
        );
      },
      onStatus: onStatus,
    );
  }

  @override
  Future<void> listen({
    required void Function(JurisdictaSpeechRecognitionResult result) onResult,
    required String localeId,
    Duration? listenFor,
    Duration? pauseFor,
    bool partialResults = true,
    bool cancelOnError = true,
    ListenMode listenMode = ListenMode.dictation,
  }) {
    return _speechToText.listen(
      onResult: (platform_speech.SpeechRecognitionResult result) {
        onResult(
          JurisdictaSpeechRecognitionResult(
            recognizedWords: result.recognizedWords,
            finalResult: result.finalResult,
          ),
        );
      },
      localeId: localeId,
      listenFor: listenFor ?? config.listenFor,
      pauseFor: pauseFor ?? config.pauseFor,
      listenOptions: SpeechListenOptions(
        partialResults: partialResults,
        cancelOnError: cancelOnError,
        listenMode: listenMode,
      ),
    );
  }

  @override
  Future<void> stop() {
    return _speechToText.stop();
  }
}

class AzureSpeechRecognizerConfig {
  const AzureSpeechRecognizerConfig({
    required this.key,
    this.region,
    this.endpoint,
  });

  final String key;
  final String? region;
  final String? endpoint;

  bool get isConfigured {
    return key.trim().isNotEmpty &&
        ((endpoint != null && endpoint!.trim().isNotEmpty) ||
            (region != null && region!.trim().isNotEmpty));
  }

  Uri recognitionUri({required String localeId}) {
    final normalizedLocale = localeId.trim().replaceAll('_', '-');
    final base = _baseEndpoint(
      endpoint: endpoint,
      region: region,
      serviceHostPrefix: 'stt',
    );
    return base.replace(
      path: _appendPath(
        base.path,
        '/speech/recognition/conversation/cognitiveservices/v1',
      ),
      queryParameters: <String, String>{
        'language': normalizedLocale,
        'format': 'detailed',
      },
    );
  }
}

class AzureSpeechRecognizer implements JurisdictaSpeechRecognizer {
  AzureSpeechRecognizer({
    required AzureSpeechRecognizerConfig config,
    AudioRecorder? recorder,
    http.Client? httpClient,
  })  : _config = config,
        _recorder = recorder ?? AudioRecorder(),
        _httpClient = httpClient ?? http.Client();

  static const int _sampleRate = 16000;
  static const int _numChannels = 1;
  static const int _bitsPerSample = 16;
  static const int _speechLevelThreshold = 900;

  final AzureSpeechRecognizerConfig _config;
  final AudioRecorder _recorder;
  final http.Client _httpClient;

  void Function(JurisdictaSpeechRecognitionError error)? _onError;
  void Function(String status)? _onStatus;
  void Function(JurisdictaSpeechRecognitionResult result)? _onResult;
  StreamSubscription<Uint8List>? _audioSubscription;
  BytesBuilder _audioBuffer = BytesBuilder(copy: false);
  String _localeId = 'en_US';
  bool _isListening = false;
  Duration _pauseFor = const Duration(seconds: 5);
  Timer? _silenceTimer;

  @override
  Future<bool> initialize({
    required void Function(JurisdictaSpeechRecognitionError error) onError,
    required void Function(String status) onStatus,
  }) async {
    _onError = onError;
    _onStatus = onStatus;
    if (!_config.isConfigured || kIsWeb) {
      return false;
    }
    return _recorder.hasPermission();
  }

  @override
  Future<void> listen({
    required void Function(JurisdictaSpeechRecognitionResult result) onResult,
    required String localeId,
    Duration? listenFor,
    Duration? pauseFor,
    bool partialResults = true,
    bool cancelOnError = true,
    ListenMode listenMode = ListenMode.dictation,
  }) async {
    _onResult = onResult;
    _localeId = localeId;
    _pauseFor = pauseFor ?? const Duration(seconds: 5);
    if (!_config.isConfigured) {
      _emitError('Azure Speech STT is not configured.', permanent: true);
      return;
    }
    if (_isListening) {
      await stop();
    }
    final hasPermission = await _recorder.hasPermission();
    if (!hasPermission) {
      _emitError('Microphone permission is not granted.', permanent: true);
      return;
    }

    _audioBuffer = BytesBuilder(copy: false);
    final stream = await _recorder.startStream(
      const RecordConfig(
        encoder: AudioEncoder.pcm16bits,
        sampleRate: _sampleRate,
        numChannels: _numChannels,
        autoGain: true,
        echoCancel: true,
        noiseSuppress: true,
      ),
    );
    _audioSubscription = stream.listen(
      (Uint8List chunk) {
        _audioBuffer.add(chunk);
        if (_containsSpeech(chunk)) {
          _resetSilenceTimer();
        }
      },
      onError: (Object error) {
        _emitError(
          'Azure Speech recorder failed: $error',
          permanent: false,
        );
      },
      cancelOnError: false,
    );
    _isListening = true;
    _resetSilenceTimer();
    _onStatus?.call('listening');
  }

  @override
  Future<void> stop() async {
    if (!_isListening) {
      return;
    }
    _isListening = false;
    _silenceTimer?.cancel();
    _silenceTimer = null;

    try {
      await _recorder.stop();
      await _audioSubscription?.cancel();
      _audioSubscription = null;

      final audioBytes = _audioBuffer.takeBytes();
      if (audioBytes.isEmpty) {
        _onResult?.call(
          const JurisdictaSpeechRecognitionResult(
            recognizedWords: '',
            finalResult: true,
          ),
        );
        _onStatus?.call('notListening');
        return;
      }

      final response = await _httpClient.post(
        _config.recognitionUri(localeId: _localeId),
        headers: <String, String>{
          'Ocp-Apim-Subscription-Key': _config.key,
          'Content-Type':
              'audio/wav; codecs=audio/pcm; samplerate=$_sampleRate',
          'Accept': 'application/json',
        },
        body: _buildWavBytes(audioBytes),
      );

      if (response.statusCode < 200 || response.statusCode >= 300) {
        _emitError(
          'Azure Speech STT request failed (${response.statusCode}).',
          permanent: false,
        );
        return;
      }

      final recognizedText = _extractRecognizedText(response.body);
      _onResult?.call(
        JurisdictaSpeechRecognitionResult(
          recognizedWords: recognizedText,
          finalResult: true,
        ),
      );
      _onStatus?.call('notListening');
    } catch (error) {
      _emitError('Azure Speech STT failed: $error', permanent: false);
    }
  }

  void _emitError(String message, {required bool permanent}) {
    _silenceTimer?.cancel();
    _silenceTimer = null;
    _onError?.call(
      JurisdictaSpeechRecognitionError(
        errorMsg: message,
        permanent: permanent,
      ),
    );
    _onStatus?.call('notListening');
  }

  void _resetSilenceTimer() {
    _silenceTimer?.cancel();
    _silenceTimer = Timer(_pauseFor, () {
      if (_isListening) {
        unawaited(stop());
      }
    });
  }

  bool _containsSpeech(Uint8List chunk) {
    if (chunk.lengthInBytes < 2) {
      return false;
    }
    final samples = ByteData.sublistView(chunk);
    for (var offset = 0; offset <= chunk.lengthInBytes - 2; offset += 2) {
      final amplitude = samples.getInt16(offset, Endian.little).abs();
      if (amplitude >= _speechLevelThreshold) {
        return true;
      }
    }
    return false;
  }

  Uint8List _buildWavBytes(Uint8List pcmBytes) {
    final header = ByteData(44);
    const byteRate = _sampleRate * _numChannels * (_bitsPerSample ~/ 8);
    const blockAlign = _numChannels * (_bitsPerSample ~/ 8);

    void writeAscii(int offset, String value) {
      for (var index = 0; index < value.length; index += 1) {
        header.setUint8(offset + index, value.codeUnitAt(index));
      }
    }

    writeAscii(0, 'RIFF');
    header.setUint32(4, 36 + pcmBytes.length, Endian.little);
    writeAscii(8, 'WAVE');
    writeAscii(12, 'fmt ');
    header.setUint32(16, 16, Endian.little);
    header.setUint16(20, 1, Endian.little);
    header.setUint16(22, _numChannels, Endian.little);
    header.setUint32(24, _sampleRate, Endian.little);
    header.setUint32(28, byteRate, Endian.little);
    header.setUint16(32, blockAlign, Endian.little);
    header.setUint16(34, _bitsPerSample, Endian.little);
    writeAscii(36, 'data');
    header.setUint32(40, pcmBytes.length, Endian.little);

    return Uint8List.fromList(<int>[
      ...header.buffer.asUint8List(),
      ...pcmBytes,
    ]);
  }

  String _extractRecognizedText(String body) {
    final decoded = jsonDecode(body);
    if (decoded is! Map<String, dynamic>) {
      return '';
    }

    final displayText = decoded['DisplayText']?.toString().trim();
    if (displayText != null && displayText.isNotEmpty) {
      return displayText;
    }

    final nbest = decoded['NBest'];
    if (nbest is List && nbest.isNotEmpty) {
      final first = nbest.first;
      if (first is Map<String, dynamic>) {
        final display = first['Display']?.toString().trim();
        if (display != null && display.isNotEmpty) {
          return display;
        }
      }
    }

    return '';
  }
}

JurisdictaSpeechRecognizer _defaultSpeechRecognizerFactory(
  SpeechServiceConfig config,
) {
  if (config.mode == SpeechMode.azure && config.hasAzureSttConfig && !kIsWeb) {
    return AzureSpeechRecognizer(
      config: AzureSpeechRecognizerConfig(
        key: config.azureKey ?? '',
        region: config.azureRegion,
        endpoint: config.azureSttEndpoint,
      ),
    );
  }
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
      endpoint: config.azureTtsEndpoint ?? config.azureEndpoint,
    ),
    fallbackSpeaker: fallbackSpeaker,
  );
}

Uri _baseEndpoint({
  required String? endpoint,
  required String? region,
  required String serviceHostPrefix,
}) {
  final explicitEndpoint = endpoint?.trim();
  if (explicitEndpoint != null && explicitEndpoint.isNotEmpty) {
    final parsed = Uri.parse(explicitEndpoint);
    if (parsed.path.isEmpty || parsed.path == '/') {
      return parsed.replace(path: '');
    }
    return parsed;
  }
  final normalizedRegion = (region ?? '').trim();
  return Uri.parse(
      'https://$normalizedRegion.$serviceHostPrefix.speech.microsoft.com');
}

String _appendPath(String existingPath, String appendedPath) {
  if (existingPath.isEmpty || existingPath == '/') {
    return appendedPath;
  }
  if (existingPath.endsWith(appendedPath)) {
    return existingPath;
  }
  final normalizedExisting = existingPath.endsWith('/')
      ? existingPath.substring(0, existingPath.length - 1)
      : existingPath;
  final normalizedAppended =
      appendedPath.startsWith('/') ? appendedPath : '/$appendedPath';
  return '$normalizedExisting$normalizedAppended';
}
