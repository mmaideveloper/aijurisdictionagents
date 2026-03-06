import 'dart:async';
import 'dart:convert';

import 'package:camera/camera.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_svg/flutter_svg.dart';
import 'package:http/http.dart' as http;
import 'package:speech_to_text/speech_recognition_error.dart';
import 'package:speech_to_text/speech_recognition_result.dart';
import 'package:speech_to_text/speech_to_text.dart';

import 'logging/app_logger.dart';

const String _apiBaseUrlOverride = String.fromEnvironment(
  'AIJ_API_BASE_URL',
  defaultValue: '',
);
const String _apiKey = String.fromEnvironment(
  'AIJ_API_KEY',
  defaultValue: 'aijuris',
);
const String _defaultCountry = String.fromEnvironment(
  'AIJ_DEFAULT_COUNTRY',
  defaultValue: 'SK',
);
const String _defaultLanguage = String.fromEnvironment(
  'AIJ_DEFAULT_LANGUAGE',
  defaultValue: 'SK',
);
const String _fallbackLanguageCode = 'SK';

const Map<String, String> _welcomeMessagesByLanguage = <String, String>{
  'SK':
      'Ahoj, som Jurisdicta. Pomozem vam s vasim pripadom. Popiste svoj problem a nahrajte relevantnu dokumentaciu.',
  'EN':
      'Hello, I am Jurisdicta. I can help you with your case. Please describe your problem and upload relevant documentation.',
  'GE':
      'Hallo, ich bin Jurisdicta. Ich kann Ihnen bei Ihrem Fall helfen. Bitte beschreiben Sie Ihr Problem und laden Sie relevante Unterlagen hoch.',
};

String _normalizeLanguageCode(String languageCode) {
  final normalized = languageCode.trim().toUpperCase();
  if (normalized == 'DE') {
    return 'GE';
  }
  switch (normalized) {
    case 'SK':
    case 'EN':
    case 'GE':
      return normalized;
    default:
      return _fallbackLanguageCode;
  }
}

String _welcomeMessageForLanguage(String languageCode) {
  final normalized = _normalizeLanguageCode(languageCode);
  return _welcomeMessagesByLanguage[normalized] ??
      _welcomeMessagesByLanguage[_fallbackLanguageCode]!;
}

String _defaultApiBaseUrl() {
  if (_apiBaseUrlOverride.trim().isNotEmpty) {
    return _apiBaseUrlOverride.trim();
  }
  if (kIsWeb) {
    return 'http://127.0.0.1:8080';
  }
  return 'http://10.0.2.2:8080';
}

enum ResponderMode { aiUserSimulator, realPerson }

class LocaleOption {
  const LocaleOption({
    required this.countryCode,
    required this.languageCode,
    required this.label,
  });

  final String countryCode;
  final String languageCode;
  final String label;
}

const List<LocaleOption> _localeOptions = <LocaleOption>[
  LocaleOption(countryCode: 'SK', languageCode: 'SK', label: 'Slovakia (SK)'),
  LocaleOption(countryCode: 'CZ', languageCode: 'CS', label: 'Czechia (CS)'),
  LocaleOption(countryCode: 'DE', languageCode: 'DE', label: 'Germany (DE)'),
  LocaleOption(
      countryCode: 'US', languageCode: 'EN', label: 'United States (EN)'),
];

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final logger = await createAppLogger();
  final apiBaseUrl = _defaultApiBaseUrl();
  await logger.info(
    'Application startup',
    <String, Object?>{
      'api_base_url': apiBaseUrl,
      'is_web': kIsWeb,
      'log_file': logger.logFilePath,
    },
  );
  final cameras = await availableCameras();
  await logger.info(
    'Camera discovery completed',
    <String, Object?>{'camera_count': cameras.length},
  );
  runApp(AIJurisdictionMobileApp(
      cameras: cameras, logger: logger, apiBaseUrl: apiBaseUrl));
}

class AIJurisdictionMobileApp extends StatelessWidget {
  const AIJurisdictionMobileApp({
    super.key,
    required this.cameras,
    required this.logger,
    required this.apiBaseUrl,
  });

  final List<CameraDescription> cameras;
  final AppLogger logger;
  final String apiBaseUrl;

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      debugShowCheckedModeBanner: false,
      title: 'AIJurisDigta',
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(seedColor: Colors.indigo),
        useMaterial3: true,
      ),
      home: ChatHomePage(
          cameras: cameras, logger: logger, apiBaseUrl: apiBaseUrl),
    );
  }
}

class ChatMessage {
  const ChatMessage({
    required this.role,
    required this.content,
    this.agentName,
    this.documentPath,
    this.createdAt,
  });

  final String role;
  final String content;
  final String? agentName;
  final String? documentPath;
  final DateTime? createdAt;
}

class StreamEvent {
  const StreamEvent({required this.event, required this.data});

  final String event;
  final Object? data;
}

class ApiClient {
  ApiClient(
      {required this.baseUri, required this.apiKey, required this.logger});

  final Uri baseUri;
  final String apiKey;
  final AppLogger logger;
  String? _sessionId;

  String? get sessionId => _sessionId;

  Map<String, String> get _headers => <String, String>{
        'Content-Type': 'application/json',
        'x-api-key': apiKey,
      };

  Map<String, String> get _headersForLog => <String, String>{
        'Content-Type': 'application/json',
        'x-api-key': '***',
      };

  Future<http.Response> _postJson({
    required String path,
    required Map<String, Object?> payload,
    required String action,
  }) async {
    final uri = baseUri.resolve(path);
    await logger.info(
      'API request',
      <String, Object?>{
        'action': action,
        'method': 'POST',
        'url': uri.toString(),
        'headers': _headersForLog,
        'payload': payload,
      },
    );
    try {
      final response = await http.post(
        uri,
        headers: _headers,
        body: jsonEncode(payload),
      );
      await logger.info(
        'API response',
        <String, Object?>{
          'action': action,
          'status_code': response.statusCode,
          'body': response.body,
        },
      );
      return response;
    } catch (error, stackTrace) {
      await logger.error(
        'API request failed',
        error,
        stackTrace,
        <String, Object?>{
          'action': action,
          'url': uri.toString(),
        },
      );
      rethrow;
    }
  }

  Future<String> _createSession({
    required ResponderMode responderMode,
    required LocaleOption locale,
  }) async {
    final discussionType =
        responderMode == ResponderMode.realPerson ? 'court' : 'advice';
    final payload = <String, Object?>{
      'discussion_type': discussionType,
      'country': locale.countryCode,
      'language': locale.languageCode,
    };
    final sessionResponse = await _postJson(
      path: '/v1/chat/sessions',
      action: 'create_session',
      payload: payload,
    );

    if (sessionResponse.statusCode < 200 || sessionResponse.statusCode >= 300) {
      await logger.info(
        'Session creation returned non-success status',
        <String, Object?>{
          'status_code': sessionResponse.statusCode,
          'body': sessionResponse.body,
        },
      );
      throw Exception(
        'Session creation failed with status ${sessionResponse.statusCode}.',
      );
    }

    final body = _decodeResponseBody(sessionResponse, action: 'create_session');
    final sessionId = body['id'] as String?;
    if (sessionId == null || sessionId.isEmpty) {
      throw Exception(
          'Session creation succeeded but no session id was returned.');
    }
    await logger.info(
      'Session created',
      <String, Object?>{
        'session_id': sessionId,
        'discussion_type': discussionType,
        'country': locale.countryCode,
        'language': locale.languageCode,
      },
    );
    return sessionId;
  }

  Future<String> _ensureSession({
    required ResponderMode responderMode,
    required LocaleOption locale,
  }) async {
    final existing = _sessionId;
    if (existing != null && existing.isNotEmpty) {
      await logger.info(
        'Reusing existing session',
        <String, Object?>{'session_id': existing},
      );
      return existing;
    }
    final created = await _createSession(
      responderMode: responderMode,
      locale: locale,
    );
    _sessionId = created;
    return created;
  }

  Future<String> sendMessage({
    required String message,
    required ResponderMode responderMode,
    required LocaleOption locale,
    String? documentPath,
  }) async {
    final sessionId = await _ensureSession(
      responderMode: responderMode,
      locale: locale,
    );
    final content = documentPath == null
        ? message
        : '$message\n\n[Attached local document path: $documentPath]';
    final payload = <String, Object?>{'content': content};

    final response = await _postJson(
      path: '/v1/chat/sessions/$sessionId/reply',
      action: 'reply',
      payload: payload,
    );

    if (response.statusCode == 404) {
      await logger.info(
        'Reply endpoint returned 404, resetting session and retrying once',
        <String, Object?>{'session_id': sessionId},
      );
      _sessionId = null;
      final retrySessionId = await _ensureSession(
        responderMode: responderMode,
        locale: locale,
      );
      final retryResponse = await _postJson(
        path: '/v1/chat/sessions/$retrySessionId/reply',
        action: 'reply_retry',
        payload: payload,
      );
      return _parseReply(retryResponse, action: 'reply_retry');
    }

    return _parseReply(response, action: 'reply');
  }

  List<StreamEvent> _parseSseBlock(String block) {
    final lines = block
        .split('\n')
        .map((line) => line.trim())
        .where((line) => line.isNotEmpty)
        .toList();
    if (lines.isEmpty) {
      return const [];
    }
    final eventLine = lines.firstWhere(
      (line) => line.startsWith('event:'),
      orElse: () => '',
    );
    final dataLine = lines.firstWhere(
      (line) => line.startsWith('data:'),
      orElse: () => '',
    );
    if (eventLine.isEmpty || dataLine.isEmpty) {
      return const [];
    }
    final event = eventLine.substring(6).trim();
    final rawData = dataLine.substring(5).trim();
    Object? data = rawData;
    try {
      data = jsonDecode(rawData);
    } catch (_) {
      data = rawData;
    }
    return <StreamEvent>[StreamEvent(event: event, data: data)];
  }

  Stream<StreamEvent> startDiscussionStream({
    required String instruction,
    required LocaleOption locale,
    required double questionTimeoutSeconds,
    required double maxDiscussionMinutes,
    required double communicationMinutes,
    String? documentPath,
  }) async* {
    _sessionId = null;
    final sessionId = await _ensureSession(
      responderMode: ResponderMode.aiUserSimulator,
      locale: locale,
    );
    final payload = <String, Object?>{
      'instruction': instruction,
      'documents': <Object?>[],
      'question_timeout_seconds': questionTimeoutSeconds,
      'max_discussion_minutes': maxDiscussionMinutes,
      'communication_minutes': communicationMinutes,
      'user_simulation_mode': 'AIUserSimulatorAgent',
    };
    if (documentPath != null && documentPath.trim().isNotEmpty) {
      await logger.info(
        'Discussion started with local document path context',
        <String, Object?>{'document_path': documentPath},
      );
    }

    final path = '/v1/chat/sessions/$sessionId/stream';
    final uri = baseUri.resolve(path);
    final request = http.Request('POST', uri)
      ..headers.addAll(_headers)
      ..body = jsonEncode(payload);
    await logger.info(
      'API stream request',
      <String, Object?>{
        'action': 'start_discussion_stream',
        'method': 'POST',
        'url': uri.toString(),
        'headers': _headersForLog,
        'payload': payload,
      },
    );

    final client = http.Client();
    try {
      final response = await client.send(request);
      if (response.statusCode < 200 || response.statusCode >= 300) {
        final body = await response.stream.bytesToString();
        await logger.info(
          'API stream response non-success',
          <String, Object?>{
            'status_code': response.statusCode,
            'body': body,
          },
        );
        throw Exception(
          'Discussion stream failed with status ${response.statusCode}: $body',
        );
      }
      var buffer = '';
      await for (final chunk in response.stream.transform(utf8.decoder)) {
        buffer += chunk;
        final blocks = buffer.split('\n\n');
        buffer = blocks.removeLast();
        for (final block in blocks) {
          final events = _parseSseBlock(block);
          for (final event in events) {
            await logger.info(
              'API stream event',
              <String, Object?>{
                'event': event.event,
                'data': event.data,
              },
            );
            yield event;
          }
        }
      }
      if (buffer.trim().isNotEmpty) {
        final trailingEvents = _parseSseBlock(buffer);
        for (final event in trailingEvents) {
          await logger.info(
            'API stream trailing event',
            <String, Object?>{
              'event': event.event,
              'data': event.data,
            },
          );
          yield event;
        }
      }
    } catch (error, stackTrace) {
      await logger.error(
        'API stream request failed',
        error,
        stackTrace,
        <String, Object?>{
          'action': 'start_discussion_stream',
          'url': uri.toString(),
        },
      );
      rethrow;
    } finally {
      client.close();
    }
  }

  Map<String, dynamic> _decodeResponseBody(
    http.Response response, {
    required String action,
  }) {
    try {
      return jsonDecode(response.body) as Map<String, dynamic>;
    } catch (error, stackTrace) {
      unawaited(
        logger.error(
          'Failed to decode API response body',
          error,
          stackTrace,
          <String, Object?>{
            'action': action,
            'status_code': response.statusCode,
            'body': response.body,
          },
        ),
      );
      rethrow;
    }
  }

  String _parseReply(http.Response response, {required String action}) {
    if (response.statusCode < 200 || response.statusCode >= 300) {
      throw Exception('API call failed with status ${response.statusCode}.');
    }

    final body = _decodeResponseBody(response, action: action);
    return body['content'] as String? ?? 'No response message.';
  }

  void resetSession() {
    unawaited(
      logger.info(
        'Session reset requested',
        <String, Object?>{'previous_session_id': _sessionId},
      ),
    );
    _sessionId = null;
  }
}

class ChatHomePage extends StatefulWidget {
  const ChatHomePage({
    super.key,
    required this.cameras,
    required this.logger,
    required this.apiBaseUrl,
  });

  final List<CameraDescription> cameras;
  final AppLogger logger;
  final String apiBaseUrl;

  @override
  State<ChatHomePage> createState() => _ChatHomePageState();
}

class _ChatHomePageState extends State<ChatHomePage> {
  static const double _questionTimeoutSeconds = 300;
  static const double _maxDiscussionMinutes = 15;
  static const double _communicationMinutes = 3;

  final TextEditingController _inputController = TextEditingController();
  final SpeechToText _speechToText = SpeechToText();

  late final ApiClient _apiClient;
  late final List<ChatMessage> _messages;
  ResponderMode _responderMode = ResponderMode.aiUserSimulator;
  late LocaleOption _selectedLocale;
  String? _documentPath;
  bool _isSending = false;
  bool _speechEnabled = false;
  bool _isListening = false;

  bool get _showLocalResponderSwitch {
    final host = Uri.parse(widget.apiBaseUrl).host.toLowerCase();
    return host == 'localhost' ||
        host == '127.0.0.1' ||
        host == '10.0.2.2' ||
        host == '0.0.0.0';
  }

  @override
  void initState() {
    super.initState();
    _selectedLocale = _localeOptions.firstWhere(
      (option) =>
          option.countryCode == _defaultCountry &&
          option.languageCode == _defaultLanguage,
      orElse: () => _localeOptions.first,
    );
    _apiClient = ApiClient(
      baseUri: Uri.parse(widget.apiBaseUrl),
      apiKey: _apiKey,
      logger: widget.logger,
    );
    final welcomeLanguage =
        _normalizeLanguageCode(_selectedLocale.languageCode);
    _messages = <ChatMessage>[
      ChatMessage(
        role: 'assistant',
        content: _welcomeMessageForLanguage(welcomeLanguage),
        agentName: 'Jurisdicta',
      ),
    ];
    unawaited(
      widget.logger.info(
        'Initial welcome message added',
        <String, Object?>{'language': welcomeLanguage},
      ),
    );
    unawaited(
      widget.logger.info(
        'Chat home initialized',
        <String, Object?>{
          'api_base_url': widget.apiBaseUrl,
          'log_file': widget.logger.logFilePath,
          'language': welcomeLanguage,
        },
      ),
    );
    unawaited(_initializeSpeechRecognition());
  }

  String _localeIdForSpeech(LocaleOption locale) {
    switch (locale.languageCode.toUpperCase()) {
      case 'SK':
        return 'sk_SK';
      case 'CS':
        return 'cs_CZ';
      case 'DE':
      case 'GE':
        return 'de_DE';
      case 'EN':
      default:
        return 'en_US';
    }
  }

  Future<void> _initializeSpeechRecognition() async {
    final enabled = await _speechToText.initialize(
      onError: _onSpeechError,
      onStatus: _onSpeechStatus,
    );
    if (!mounted) {
      return;
    }
    setState(() {
      _speechEnabled = enabled;
    });
    await widget.logger.info(
      'Speech recognition initialized',
      <String, Object?>{'enabled': enabled},
    );
  }

  void _onSpeechResult(SpeechRecognitionResult result) {
    if (!mounted) {
      return;
    }
    setState(() {
      _inputController.text = result.recognizedWords;
      _inputController.selection = TextSelection.fromPosition(
        TextPosition(offset: _inputController.text.length),
      );
    });
  }

  void _onSpeechStatus(String status) {
    if (!mounted) {
      return;
    }
    final isListening = status == 'listening';
    setState(() {
      _isListening = isListening;
    });
    unawaited(
      widget.logger.info(
        'Speech status changed',
        <String, Object?>{'status': status},
      ),
    );
  }

  void _onSpeechError(SpeechRecognitionError error) {
    if (!mounted) {
      return;
    }
    setState(() {
      _isListening = false;
    });
    _showSnackbar('Speech recognition error: ${error.errorMsg}');
    unawaited(
      widget.logger.error(
        'Speech recognition error',
        Exception(error.errorMsg),
        StackTrace.current,
        <String, Object?>{'permanent': error.permanent},
      ),
    );
  }

  Future<void> _toggleSpeechInput() async {
    if (!_speechEnabled) {
      _showSnackbar('Speech recognition is unavailable on this device.');
      return;
    }
    if (_isListening) {
      await _speechToText.stop();
      return;
    }
    await _speechToText.listen(
      onResult: _onSpeechResult,
      partialResults: true,
      localeId: _localeIdForSpeech(_selectedLocale),
      listenMode: ListenMode.dictation,
    );
  }

  void _updateWelcomeMessageForLocale() {
    if (_messages.isEmpty) {
      return;
    }
    final firstMessage = _messages.first;
    final isInitialWelcome = firstMessage.role == 'assistant' &&
        firstMessage.agentName == 'Jurisdicta' &&
        firstMessage.createdAt == null;
    if (!isInitialWelcome) {
      return;
    }
    final welcomeLanguage =
        _normalizeLanguageCode(_selectedLocale.languageCode);
    _messages[0] = ChatMessage(
      role: 'assistant',
      content: _welcomeMessageForLanguage(welcomeLanguage),
      agentName: 'Jurisdicta',
    );
  }

  @override
  void dispose() {
    _speechToText.stop();
    _inputController.dispose();
    super.dispose();
  }

  Future<void> _captureDocument() async {
    if (widget.cameras.isEmpty) {
      await widget.logger
          .info('Document capture requested with no available camera');
      _showSnackbar('No camera available on this device.');
      return;
    }

    final path = await Navigator.of(context).push<String>(
      MaterialPageRoute<String>(
        builder: (_) => CameraCapturePage(camera: widget.cameras.first),
      ),
    );
    if (!mounted) {
      return;
    }

    if (path != null) {
      setState(() {
        _documentPath = path;
      });
      await widget.logger.info(
        'Document captured',
        <String, Object?>{'document_path': path},
      );
      _showSnackbar('Document added from camera.');
    }
  }

  Future<void> _sendMessage() async {
    final text = _inputController.text.trim();
    if (text.isEmpty || _isSending) {
      return;
    }
    await widget.logger.info(
      'User message submission',
      <String, Object?>{
        'message_length': text.length,
        'has_document_path': _documentPath != null,
        'responder_mode': _responderMode.name,
      },
    );

    setState(() {
      _isSending = true;
      _messages.add(
        ChatMessage(
          role: 'user',
          content: text,
          documentPath: _documentPath,
          createdAt: DateTime.now(),
        ),
      );
    });

    _inputController.clear();

    try {
      if (_responderMode == ResponderMode.aiUserSimulator) {
        await widget.logger.info(
          'Starting AI user simulator discussion stream',
          <String, Object?>{
            'question_timeout_seconds': _questionTimeoutSeconds,
            'max_discussion_minutes': _maxDiscussionMinutes,
            'communication_minutes': _communicationMinutes,
          },
        );
        await for (final event in _apiClient.startDiscussionStream(
          instruction: text,
          locale: _selectedLocale,
          questionTimeoutSeconds: _questionTimeoutSeconds,
          maxDiscussionMinutes: _maxDiscussionMinutes,
          communicationMinutes: _communicationMinutes,
          documentPath: _documentPath,
        )) {
          if (event.event == 'message' && event.data is Map) {
            final payload = Map<String, dynamic>.from(event.data as Map);
            final role = (payload['role'] as String? ?? 'assistant')
                .toLowerCase()
                .trim();
            final content = payload['content'] as String? ?? '';
            final agentName = payload['agent_name'] as String?;
            if (content.isEmpty) {
              continue;
            }
            if (!mounted) {
              continue;
            }
            setState(() {
              _messages.add(
                ChatMessage(
                  role: role,
                  content: content,
                  agentName: agentName,
                  createdAt: DateTime.now(),
                ),
              );
            });
          }
          if (event.event == 'error') {
            throw Exception('Discussion stream reported error: ${event.data}');
          }
        }
      } else {
        final reply = await _apiClient.sendMessage(
          message: text,
          responderMode: _responderMode,
          locale: _selectedLocale,
          documentPath: _documentPath,
        );
        await widget.logger.info(
          'Assistant reply received',
          <String, Object?>{
            'reply_length': reply.length,
            'responder_mode': _responderMode.name,
          },
        );
        if (mounted) {
          setState(() {
            _messages.add(
              ChatMessage(
                role: 'assistant',
                content: reply,
                createdAt: DateTime.now(),
              ),
            );
          });
        }
      }
    } catch (error, stackTrace) {
      await widget.logger.error(
        'Failed to send message to API',
        error,
        stackTrace,
        <String, Object?>{
          'api_base_url': widget.apiBaseUrl,
          'responder_mode': _responderMode.name,
        },
      );
      _showSnackbar('Failed to reach API at ${widget.apiBaseUrl}: $error');
    } finally {
      if (mounted) {
        setState(() {
          _isSending = false;
        });
      }
    }
  }

  void _showSnackbar(String message) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(message)),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Stack(
        children: [
          Positioned.fill(
            child: DecoratedBox(
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment.topCenter,
                  end: Alignment.bottomCenter,
                  colors: <Color>[
                    const Color(0xFF041B59),
                    const Color(0xFF1388E9),
                    const Color(0xFF041B59),
                  ],
                ),
              ),
            ),
          ),
          Positioned.fill(
            child: Opacity(
              opacity: 0.08,
              child: SvgPicture.asset(
                'assets/branding/hero-footer.svg',
                fit: BoxFit.cover,
              ),
            ),
          ),
          SafeArea(
            child: Column(
              children: [
                Padding(
                  padding: const EdgeInsets.fromLTRB(12, 8, 12, 8),
                  child: Container(
                    padding: const EdgeInsets.all(12),
                    decoration: BoxDecoration(
                      color: Colors.white.withOpacity(0.94),
                      borderRadius: BorderRadius.circular(14),
                    ),
                    child: Row(
                      children: [
                        SizedBox(
                          width: 48,
                          height: 48,
                          child: Image.asset(
                            'assets/branding/login-shield.png',
                            fit: BoxFit.contain,
                            filterQuality: FilterQuality.high,
                          ),
                        ),
                        const SizedBox(width: 10),
                        const Expanded(
                          child: Text(
                            'AIJurisDigta',
                            style: TextStyle(
                              fontSize: 18,
                              fontWeight: FontWeight.w700,
                              color: Color(0xFF0A2F6B),
                            ),
                          ),
                        ),
                        FilledButton.tonal(
                          onPressed: () => _showSnackbar('Login UI placeholder'),
                          child: const Text('Sign in'),
                        ),
                      ],
                    ),
                  ),
                ),
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 12),
                  child: Row(
                    mainAxisAlignment: MainAxisAlignment.spaceEvenly,
                    children: const [
                      _BrandIcon(path: 'assets/branding/icon-ai-head.svg'),
                      _BrandIcon(path: 'assets/branding/icon-scale.svg'),
                      _BrandIcon(path: 'assets/branding/icon-doc-check.svg'),
                      _BrandIcon(path: 'assets/branding/icon-court.svg'),
                    ],
                  ),
                ),
                const SizedBox(height: 8),
              if (_documentPath != null)
                MaterialBanner(
                  content: Text('Attached document: $_documentPath'),
                  leading: const Icon(Icons.attachment),
                  actions: [
                    TextButton(
                      onPressed: () {
                        setState(() {
                          _documentPath = null;
                        });
                        unawaited(
                          widget.logger.info('Attached document path cleared'),
                        );
                      },
                      child: const Text('CLEAR'),
                    ),
                  ],
                ),
              Expanded(
                child: ListView.builder(
                  reverse: true,
                  padding: const EdgeInsets.all(12),
                  itemCount: _messages.length,
                  itemBuilder: (context, index) {
                    final message = _messages[_messages.length - 1 - index];
                    final isUser = message.role == 'user';
                    final speaker = isUser
                        ? 'You'
                        : (message.agentName?.trim().isNotEmpty ?? false)
                            ? message.agentName!
                            : 'Assistant';
                    return Align(
                      alignment:
                          isUser ? Alignment.centerRight : Alignment.centerLeft,
                      child: Container(
                        constraints: const BoxConstraints(maxWidth: 320),
                        margin: const EdgeInsets.only(bottom: 10),
                        padding: const EdgeInsets.all(12),
                        decoration: BoxDecoration(
                          color: isUser
                              ? Theme.of(context).colorScheme.primaryContainer
                              : Theme.of(context)
                                  .colorScheme
                                  .surfaceContainerHighest,
                          borderRadius: BorderRadius.circular(12),
                        ),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              speaker,
                              style: Theme.of(context).textTheme.labelMedium,
                            ),
                            const SizedBox(height: 4),
                            Text(message.content),
                            if (message.documentPath != null)
                              Padding(
                                padding: const EdgeInsets.only(top: 8),
                                child: Text(
                                  'Document: ${message.documentPath}',
                                  style: Theme.of(context).textTheme.bodySmall,
                                ),
                              ),
                          ],
                        ),
                      ),
                    );
                  },
                ),
              ),
              Padding(
                padding: const EdgeInsets.fromLTRB(12, 6, 12, 4),
                child: Container(
                  padding: const EdgeInsets.symmetric(horizontal: 10),
                  decoration: BoxDecoration(
                    color: Colors.white.withOpacity(0.9),
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: Column(
                    children: [
                      Row(
                        children: [
                          const Text('Language & Country:'),
                          const SizedBox(width: 8),
                          Expanded(
                            child: DropdownButton<LocaleOption>(
                              isExpanded: true,
                              value: _selectedLocale,
                              onChanged: (locale) {
                                if (locale == null) {
                                  return;
                                }
                                setState(() {
                                  _selectedLocale = locale;
                                  _updateWelcomeMessageForLocale();
                                });
                                if (_isListening) {
                                  unawaited(_speechToText.stop());
                                }
                                unawaited(
                                  widget.logger.info(
                                    'Locale changed',
                                    <String, Object?>{
                                      'country': locale.countryCode,
                                      'language': locale.languageCode,
                                    },
                                  ),
                                );
                                _apiClient.resetSession();
                              },
                              items: _localeOptions
                                  .map(
                                    (locale) => DropdownMenuItem<LocaleOption>(
                                      value: locale,
                                      child: Text(locale.label),
                                    ),
                                  )
                                  .toList(),
                            ),
                          ),
                        ],
                      ),
                      if (_showLocalResponderSwitch)
                        Row(
                          children: [
                            const Text('Local mode:'),
                            const SizedBox(width: 8),
                            Expanded(
                              child: DropdownButton<ResponderMode>(
                                isExpanded: true,
                                value: _responderMode,
                                onChanged: (mode) {
                                  if (mode == null) {
                                    return;
                                  }
                                  setState(() {
                                    _responderMode = mode;
                                  });
                                  unawaited(
                                    widget.logger.info(
                                      'Responder mode changed',
                                      <String, Object?>{
                                        'responder_mode': mode.name,
                                      },
                                    ),
                                  );
                                  _apiClient.resetSession();
                                },
                                items: const [
                                  DropdownMenuItem(
                                    value: ResponderMode.aiUserSimulator,
                                    child: Text('AI User Simulator Agent'),
                                  ),
                                  DropdownMenuItem(
                                    value: ResponderMode.realPerson,
                                    child: Text('Read User'),
                                  ),
                                ],
                              ),
                            ),
                          ],
                        ),
                    ],
                  ),
                ),
              ),
              Padding(
                padding: const EdgeInsets.fromLTRB(12, 2, 12, 12),
                child: Row(
                  children: [
                      IconButton(
                        onPressed: _captureDocument,
                        icon: const Icon(Icons.document_scanner),
                        tooltip: 'Upload documents',
                      ),
                      const SizedBox(width: 8),
                      Expanded(
                        child: TextField(
                          controller: _inputController,
                          minLines: 1,
                          maxLines: 4,
                          textInputAction: TextInputAction.send,
                          onSubmitted: (_) => _sendMessage(),
                          decoration: InputDecoration(
                            hintText:
                                _responderMode == ResponderMode.aiUserSimulator
                                    ? 'Describe the case to start discussion...'
                                    : 'Ask your legal question...',
                            filled: true,
                            fillColor: Colors.white,
                            border: const OutlineInputBorder(),
                          ),
                        ),
                      ),
                      const SizedBox(width: 8),
                      IconButton(
                        onPressed: _toggleSpeechInput,
                        icon: Icon(
                          _isListening ? Icons.mic : Icons.mic_none,
                          color: _isListening
                              ? Theme.of(context).colorScheme.primary
                              : null,
                        ),
                        tooltip: _isListening
                            ? 'Stop speech input'
                            : 'Add question/answer by speech',
                      ),
                      const SizedBox(width: 8),
                      IconButton(
                        onPressed: _isSending ? null : _sendMessage,
                        icon: _isSending
                            ? const SizedBox(
                                width: 16,
                                height: 16,
                                child:
                                    CircularProgressIndicator(strokeWidth: 2),
                              )
                            : const Icon(Icons.send),
                        tooltip: _responderMode == ResponderMode.aiUserSimulator
                            ? 'Start AI discussion'
                            : 'Send to API',
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _BrandIcon extends StatelessWidget {
  const _BrandIcon({required this.path});

  final String path;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 52,
      height: 52,
      padding: const EdgeInsets.all(6),
      decoration: BoxDecoration(
        color: Colors.white.withOpacity(0.9),
        borderRadius: BorderRadius.circular(12),
      ),
      child: SvgPicture.asset(path),
    );
  }
}

class CameraCapturePage extends StatefulWidget {
  const CameraCapturePage({super.key, required this.camera});

  final CameraDescription camera;

  @override
  State<CameraCapturePage> createState() => _CameraCapturePageState();
}

class _CameraCapturePageState extends State<CameraCapturePage> {
  CameraController? _controller;
  Future<void>? _initializeControllerFuture;

  @override
  void initState() {
    super.initState();
    _controller = CameraController(widget.camera, ResolutionPreset.medium);
    _initializeControllerFuture = _controller!.initialize();
  }

  @override
  void dispose() {
    _controller?.dispose();
    super.dispose();
  }

  Future<void> _takePicture() async {
    final controller = _controller;
    if (controller == null) {
      return;
    }

    await _initializeControllerFuture;
    final image = await controller.takePicture();
    if (mounted) {
      Navigator.of(context).pop(image.path);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Capture document')),
      body: FutureBuilder<void>(
        future: _initializeControllerFuture,
        builder: (context, snapshot) {
          if (snapshot.connectionState == ConnectionState.done &&
              _controller != null) {
            return Stack(
              children: [
                Positioned.fill(child: CameraPreview(_controller!)),
                Positioned(
                  bottom: 24,
                  left: 0,
                  right: 0,
                  child: Center(
                    child: FloatingActionButton.extended(
                      onPressed: _takePicture,
                      icon: const Icon(Icons.camera),
                      label: const Text('Use photo'),
                    ),
                  ),
                ),
              ],
            );
          }

          if (snapshot.hasError) {
            return Center(
              child: Text('Could not initialize camera: ${snapshot.error}'),
            );
          }

          return const Center(child: CircularProgressIndicator());
        },
      ),
    );
  }
}
