import 'dart:async';
import 'dart:convert';

import 'package:camera/camera.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_svg/flutter_svg.dart';
import 'package:http/http.dart' as http;
import 'package:package_info_plus/package_info_plus.dart';
import 'package:speech_to_text/speech_recognition_error.dart';
import 'package:speech_to_text/speech_recognition_result.dart';
import 'package:speech_to_text/speech_to_text.dart';
import 'package:url_launcher/url_launcher.dart';

import 'auth/local_auth_store.dart';
import 'logging/app_logger.dart';
import 'platform/file_saver.dart';

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
const String _githubOwner = String.fromEnvironment(
  'AIJ_GITHUB_OWNER',
  defaultValue: 'mmaideveloper',
);
const String _githubRepo = String.fromEnvironment(
  'AIJ_GITHUB_REPO',
  defaultValue: 'aijurisdictionagents',
);

const Map<String, String> _welcomeMessagesByLanguage = <String, String>{
  'SK':
      'Ahoj, som Jurisdicta. Pomozem vam s vasim pripadom. Popiste svoj problem a nahrajte relevantnu dokumentaciu.',
  'EN':
      'Hello, I am Jurisdicta. I can help you with your case. Please describe your problem and upload relevant documentation.',
  'GE':
      'Hallo, ich bin Jurisdicta. Ich kann Ihnen bei Ihrem Fall helfen. Bitte beschreiben Sie Ihr Problem und laden Sie relevante Unterlagen hoch.',
};

const Map<String, String> _sessionExpiredMessagesByLanguage = <String, String>{
  'SK':
      'Relacia vyprsala. Vytvorili sme novu relaciu. Prosim, odoslite poslednu spravu znova.',
  'EN':
      'Your session expired. A new session was created. Please send your last message again.',
  'GE':
      'Ihre Sitzung ist abgelaufen. Eine neue Sitzung wurde erstellt. Bitte senden Sie Ihre letzte Nachricht erneut.',
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

String _sessionExpiredMessageForLanguage(String languageCode) {
  final normalized = _normalizeLanguageCode(languageCode);
  return _sessionExpiredMessagesByLanguage[normalized] ??
      _sessionExpiredMessagesByLanguage[_fallbackLanguageCode]!;
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
  List<CameraDescription> cameras = <CameraDescription>[];
  try {
    cameras = await availableCameras();
    await logger.info(
      'Camera discovery completed',
      <String, Object?>{'camera_count': cameras.length},
    );
  } catch (error, stackTrace) {
    await logger.error(
      'Camera discovery failed',
      error,
      stackTrace,
    );
  }
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
      home: AuthGatePage(
        cameras: cameras,
        logger: logger,
        apiBaseUrl: apiBaseUrl,
      ),
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

String _displayContentForMessage(ChatMessage message) {
  if (message.role != 'assistant') {
    return message.content;
  }
  return _stripCaseUpdateJson(message.content);
}

String _stripCaseUpdateJson(String content) {
  final marker = RegExp(
    r'\*{0,2}\s*CASE_UPDATE_JSON\s*:?\s*\*{0,2}',
    caseSensitive: false,
  );
  final match = marker.firstMatch(content);
  if (match == null) {
    return content.trimRight();
  }
  final visible = content.substring(0, match.start).trimRight();
  return visible.isEmpty ? content.trimRight() : visible;
}

class StreamEvent {
  const StreamEvent({required this.event, required this.data});

  final String event;
  final Object? data;
}

class ExportFilePayload {
  const ExportFilePayload({
    required this.bytes,
    required this.filename,
    required this.contentType,
  });

  final Uint8List bytes;
  final String filename;
  final String contentType;
}

class SessionExpiredException implements Exception {
  const SessionExpiredException();

  @override
  String toString() => 'Session expired and was recreated.';
}

class _SemanticVersion implements Comparable<_SemanticVersion> {
  const _SemanticVersion({
    required this.major,
    required this.minor,
    required this.patch,
    required this.build,
  });

  final int major;
  final int minor;
  final int patch;
  final int build;

  static _SemanticVersion? tryParse(String input) {
    final match = RegExp(r'(\d+)\.(\d+)\.(\d+)(?:\+(\d+))?').firstMatch(input);
    if (match == null) {
      return null;
    }
    return _SemanticVersion(
      major: int.tryParse(match.group(1) ?? '') ?? 0,
      minor: int.tryParse(match.group(2) ?? '') ?? 0,
      patch: int.tryParse(match.group(3) ?? '') ?? 0,
      build: int.tryParse(match.group(4) ?? '') ?? 0,
    );
  }

  @override
  int compareTo(_SemanticVersion other) {
    final majorDiff = major.compareTo(other.major);
    if (majorDiff != 0) {
      return majorDiff;
    }
    final minorDiff = minor.compareTo(other.minor);
    if (minorDiff != 0) {
      return minorDiff;
    }
    final patchDiff = patch.compareTo(other.patch);
    if (patchDiff != 0) {
      return patchDiff;
    }
    return build.compareTo(other.build);
  }

  @override
  String toString() {
    if (build > 0) {
      return '$major.$minor.$patch+$build';
    }
    return '$major.$minor.$patch';
  }
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

  Future<http.Response> _get({
    required String path,
    required String action,
  }) async {
    final uri = baseUri.resolve(path);
    await logger.info(
      'API request',
      <String, Object?>{
        'action': action,
        'method': 'GET',
        'url': uri.toString(),
        'headers': _headersForLog,
      },
    );
    try {
      final response = await http.get(uri, headers: _headers);
      await logger.info(
        'API response',
        <String, Object?>{
          'action': action,
          'status_code': response.statusCode,
          'content_type': response.headers['content-type'],
          'bytes': response.bodyBytes.length,
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

  String _extractErrorDetailFromBody(String body) {
    final normalizedBody = body.trim();
    if (normalizedBody.isEmpty) {
      return body;
    }
    try {
      final decoded = jsonDecode(normalizedBody);
      if (decoded is Map<String, dynamic>) {
        final detail = decoded['detail'] as Object?;
        if (detail is String && detail.trim().isNotEmpty) {
          return detail.trim();
        }
      }
    } catch (_) {
      // Fall back to raw response body when JSON decoding fails.
    }
    return body;
  }

  String _extractErrorDetail(http.Response response) {
    return _extractErrorDetailFromBody(response.body);
  }

  bool _isMissingSessionDetail(String detail) {
    final normalized = detail.toLowerCase();
    return normalized.contains('session') && normalized.contains('not found');
  }

  bool _isMissingSessionResponse(http.Response response) {
    if (response.statusCode != 404) {
      return false;
    }
    final detail = _extractErrorDetail(response);
    return _isMissingSessionDetail(detail);
  }

  Future<String> _recreateSessionAfterMissing({
    required String operation,
    required String missingSessionId,
    required ResponderMode responderMode,
    required LocaleOption locale,
  }) async {
    await logger.info(
      'Missing session detected, recreating session',
      <String, Object?>{
        'operation': operation,
        'missing_session_id': missingSessionId,
      },
    );
    _sessionId = null;
    final recreated = await _ensureSession(
      responderMode: responderMode,
      locale: locale,
    );
    await logger.info(
      'Session recreated',
      <String, Object?>{
        'operation': operation,
        'recreated_session_id': recreated,
      },
    );
    return recreated;
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

    if (_isMissingSessionResponse(response)) {
      final retrySessionId = await _recreateSessionAfterMissing(
        operation: 'reply',
        missingSessionId: sessionId,
        responderMode: responderMode,
        locale: locale,
      );
      final retryResponse = await _postJson(
        path: '/v1/chat/sessions/$retrySessionId/reply',
        action: 'reply_retry',
        payload: payload,
      );
      if (_isMissingSessionResponse(retryResponse)) {
        await _recreateSessionAfterMissing(
          operation: 'reply_retry',
          missingSessionId: retrySessionId,
          responderMode: responderMode,
          locale: locale,
        );
        throw const SessionExpiredException();
      }
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

    for (var attempt = 0; attempt < 2; attempt++) {
      final sessionId = await _ensureSession(
        responderMode: ResponderMode.aiUserSimulator,
        locale: locale,
      );
      final path = '/v1/chat/sessions/$sessionId/stream';
      final uri = baseUri.resolve(path);
      final request = http.Request('POST', uri)
        ..headers.addAll(_headers)
        ..body = jsonEncode(payload);
      await logger.info(
        'API stream request',
        <String, Object?>{
          'action': 'start_discussion_stream',
          'attempt': attempt + 1,
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
          final detail = _extractErrorDetailFromBody(body);
          await logger.info(
            'API stream response non-success',
            <String, Object?>{
              'attempt': attempt + 1,
              'status_code': response.statusCode,
              'detail': detail,
            },
          );
          if (response.statusCode == 404 && _isMissingSessionDetail(detail)) {
            await _recreateSessionAfterMissing(
              operation: 'start_discussion_stream',
              missingSessionId: sessionId,
              responderMode: ResponderMode.aiUserSimulator,
              locale: locale,
            );
            if (attempt == 0) {
              continue;
            }
            throw const SessionExpiredException();
          }
          throw Exception(
            'Discussion stream failed with status ${response.statusCode}: $detail',
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
        return;
      } catch (error, stackTrace) {
        await logger.error(
          'API stream request failed',
          error,
          stackTrace,
          <String, Object?>{
            'action': 'start_discussion_stream',
            'attempt': attempt + 1,
            'url': uri.toString(),
          },
        );
        rethrow;
      } finally {
        client.close();
      }
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
      final detail = _extractErrorDetail(response);
      if (_isMissingSessionDetail(detail)) {
        throw const SessionExpiredException();
      }
      throw Exception(
        'API call failed with status ${response.statusCode}: $detail',
      );
    }

    final body = _decodeResponseBody(response, action: action);
    return body['content'] as String? ?? 'No response message.';
  }

  String _fallbackExportFilename({
    required String kind,
    required String sessionId,
  }) {
    final now = DateTime.now();
    final stamp =
        '${now.year.toString().padLeft(4, '0')}${now.month.toString().padLeft(2, '0')}${now.day.toString().padLeft(2, '0')}${now.hour.toString().padLeft(2, '0')}${now.minute.toString().padLeft(2, '0')}${now.second.toString().padLeft(2, '0')}';
    final docName =
        kind == 'document' ? 'final-document' : 'discussion-summary';
    return '$sessionId-$stamp-$docName.pdf';
  }

  String? _filenameFromContentDisposition(String? headerValue) {
    if (headerValue == null || headerValue.trim().isEmpty) {
      return null;
    }
    final match = RegExp(r'filename="([^"]+)"', caseSensitive: false)
        .firstMatch(headerValue);
    if (match == null) {
      return null;
    }
    final value = match.group(1)?.trim();
    if (value == null || value.isEmpty) {
      return null;
    }
    return value;
  }

  Future<ExportFilePayload> downloadExportPdf({
    required String kind,
    required ResponderMode responderMode,
    required LocaleOption locale,
  }) async {
    if (kind != 'summary' && kind != 'document') {
      throw Exception('Unsupported PDF export kind: $kind');
    }
    final sessionId = _sessionId;
    if (sessionId == null || sessionId.isEmpty) {
      throw Exception('No active session. Start a discussion first.');
    }
    final response = await _get(
      path: '/v1/chat/sessions/$sessionId/export?format=pdf&kind=$kind',
      action: 'export_pdf_$kind',
    );
    if (response.statusCode < 200 || response.statusCode >= 300) {
      final detail = _extractErrorDetail(response);
      if (_isMissingSessionDetail(detail)) {
        await _recreateSessionAfterMissing(
          operation: 'export_pdf_$kind',
          missingSessionId: sessionId,
          responderMode: responderMode,
          locale: locale,
        );
        throw const SessionExpiredException();
      }
      throw Exception(
        'PDF export failed with status ${response.statusCode}: $detail',
      );
    }
    final filename = _filenameFromContentDisposition(
          response.headers['content-disposition'],
        ) ??
        _fallbackExportFilename(kind: kind, sessionId: sessionId);
    final contentType = response.headers['content-type'] ?? 'application/pdf';
    return ExportFilePayload(
      bytes: response.bodyBytes,
      filename: filename,
      contentType: contentType,
    );
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

class AuthGatePage extends StatefulWidget {
  const AuthGatePage({
    super.key,
    required this.cameras,
    required this.logger,
    required this.apiBaseUrl,
  });

  final List<CameraDescription> cameras;
  final AppLogger logger;
  final String apiBaseUrl;

  @override
  State<AuthGatePage> createState() => _AuthGatePageState();
}

class _AuthGatePageState extends State<AuthGatePage> {
  late final LocalAuthStore _authStore;
  LocalAuthUser? _currentUser;
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _authStore = LocalAuthStore(
      baseUri: Uri.parse(widget.apiBaseUrl),
      apiKey: _apiKey,
    );
    unawaited(_loadSession());
  }

  Future<void> _loadSession() async {
    final user = await _authStore.getCurrentUser();
    if (!mounted) {
      return;
    }
    setState(() {
      _currentUser = user;
      _loading = false;
    });
  }

  Future<void> _handleSignedIn(LocalAuthUser user) async {
    if (!mounted) {
      return;
    }
    setState(() {
      _currentUser = user;
    });
  }

  Future<void> _handleSignedOut() async {
    await _authStore.signOut();
    if (!mounted) {
      return;
    }
    setState(() {
      _currentUser = null;
    });
  }

  void _handleProfileUpdated(LocalAuthUser user) {
    if (!mounted) {
      return;
    }
    setState(() {
      _currentUser = user;
    });
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) {
      return const Scaffold(
        body: Center(child: CircularProgressIndicator()),
      );
    }
    final user = _currentUser;
    if (user == null) {
      return AuthEntryPage(
        authStore: _authStore,
        logger: widget.logger,
        onSignedIn: _handleSignedIn,
      );
    }
    return ChatHomePage(
      cameras: widget.cameras,
      logger: widget.logger,
      apiBaseUrl: widget.apiBaseUrl,
      signedInUser: user,
      authStore: _authStore,
      onSignedOut: _handleSignedOut,
      onProfileUpdated: _handleProfileUpdated,
    );
  }
}

class AuthEntryPage extends StatefulWidget {
  const AuthEntryPage({
    super.key,
    required this.authStore,
    required this.logger,
    required this.onSignedIn,
  });

  final LocalAuthStore authStore;
  final AppLogger logger;
  final ValueChanged<LocalAuthUser> onSignedIn;

  @override
  State<AuthEntryPage> createState() => _AuthEntryPageState();
}

class _AuthEntryPageState extends State<AuthEntryPage>
    with SingleTickerProviderStateMixin {
  late final TabController _tabController;
  final TextEditingController _signInPhoneController = TextEditingController();
  final TextEditingController _signInEmailController = TextEditingController();
  final TextEditingController _signInPasswordController =
      TextEditingController();
  final TextEditingController _signUpPhoneController = TextEditingController();
  final TextEditingController _signUpEmailController = TextEditingController();
  final TextEditingController _signUpPasswordController =
      TextEditingController();
  final TextEditingController _signUpFirstNameController =
      TextEditingController();
  final TextEditingController _signUpLastNameController =
      TextEditingController();
  bool _showEmailPasswordFallback = false;
  bool _isBusy = false;

  @override
  void initState() {
    super.initState();
    _tabController = TabController(length: 2, vsync: this);
    unawaited(_loadRememberedPhoneNumber());
  }

  @override
  void dispose() {
    _tabController.dispose();
    _signInPhoneController.dispose();
    _signInEmailController.dispose();
    _signInPasswordController.dispose();
    _signUpPhoneController.dispose();
    _signUpEmailController.dispose();
    _signUpPasswordController.dispose();
    _signUpFirstNameController.dispose();
    _signUpLastNameController.dispose();
    super.dispose();
  }

  void _showSnackbar(String message) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(message)),
    );
  }

  Future<void> _loadRememberedPhoneNumber() async {
    final lastPhoneNumber = await widget.authStore.getLastPhoneNumber();
    if (!mounted || lastPhoneNumber == null || lastPhoneNumber.isEmpty) {
      return;
    }
    _signInPhoneController.text = lastPhoneNumber;
  }

  Future<void> _signInByPhone() async {
    if (_isBusy) {
      return;
    }
    setState(() {
      _isBusy = true;
    });
    try {
      final user = await widget.authStore.signInByPhone(
        _signInPhoneController.text,
      );
      if (user != null) {
        await widget.logger.info(
          'User signed in automatically by phone',
          <String, Object?>{'phone': user.phoneNumber},
        );
        widget.onSignedIn(user);
        return;
      }
      if (!mounted) {
        return;
      }
      setState(() {
        _showEmailPasswordFallback = true;
      });
      _showSnackbar(
        'Phone number not found. Sign in using email and password.',
      );
    } catch (error, stackTrace) {
      await widget.logger.error(
        'Sign-in by phone failed',
        error,
        stackTrace,
      );
      _showSnackbar('Sign in failed: $error');
    } finally {
      if (mounted) {
        setState(() {
          _isBusy = false;
        });
      }
    }
  }

  Future<void> _signInByEmailPassword() async {
    if (_isBusy) {
      return;
    }
    setState(() {
      _isBusy = true;
    });
    try {
      final user = await widget.authStore.signInByEmailPassword(
        email: _signInEmailController.text,
        password: _signInPasswordController.text,
      );
      if (user == null) {
        _showSnackbar('Invalid email or password.');
        return;
      }
      await widget.logger.info(
        'User signed in by email/password',
        <String, Object?>{'phone': user.phoneNumber, 'email': user.email},
      );
      widget.onSignedIn(user);
    } catch (error, stackTrace) {
      await widget.logger.error(
        'Sign-in by email/password failed',
        error,
        stackTrace,
      );
      _showSnackbar('Sign in failed: $error');
    } finally {
      if (mounted) {
        setState(() {
          _isBusy = false;
        });
      }
    }
  }

  Future<void> _signUp() async {
    if (_isBusy) {
      return;
    }
    setState(() {
      _isBusy = true;
    });
    try {
      final user = await widget.authStore.signUp(
        SignUpInput(
          phoneNumber: _signUpPhoneController.text,
          email: _signUpEmailController.text,
          password: _signUpPasswordController.text,
          firstName: _signUpFirstNameController.text,
          lastName: _signUpLastNameController.text,
        ),
      );
      await widget.logger.info(
        'User signed up',
        <String, Object?>{'phone': user.phoneNumber, 'email': user.email},
      );
      widget.onSignedIn(user);
    } catch (error, stackTrace) {
      await widget.logger.error(
        'Sign-up failed',
        error,
        stackTrace,
      );
      _showSnackbar('Sign up failed: $error');
    } finally {
      if (mounted) {
        setState(() {
          _isBusy = false;
        });
      }
    }
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
          SafeArea(
            child: Center(
              child: ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 560),
                child: Card(
                  margin: const EdgeInsets.all(16),
                  child: Padding(
                    padding: const EdgeInsets.all(16),
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        const SizedBox(height: 8),
                        SizedBox(
                          width: 64,
                          height: 64,
                          child: Image.asset(
                            'assets/branding/login-shield.png',
                            fit: BoxFit.contain,
                          ),
                        ),
                        const SizedBox(height: 8),
                        const Text(
                          'AIJurisDigta',
                          style: TextStyle(
                            fontSize: 22,
                            fontWeight: FontWeight.w700,
                            color: Color(0xFF0A2F6B),
                          ),
                        ),
                        const SizedBox(height: 16),
                        TabBar(
                          controller: _tabController,
                          tabs: const [
                            Tab(text: 'Sign in'),
                            Tab(text: 'Sign up'),
                          ],
                        ),
                        const SizedBox(height: 12),
                        SizedBox(
                          height: 420,
                          child: TabBarView(
                            controller: _tabController,
                            children: [
                              SingleChildScrollView(
                                child: Column(
                                  children: [
                                    TextField(
                                      controller: _signInPhoneController,
                                      keyboardType: TextInputType.phone,
                                      autofillHints: const <String>[
                                        AutofillHints.telephoneNumber,
                                        AutofillHints.username,
                                      ],
                                      decoration: const InputDecoration(
                                        labelText: 'Phone number',
                                        hintText: '+421900000000',
                                      ),
                                    ),
                                    const SizedBox(height: 12),
                                    SizedBox(
                                      width: double.infinity,
                                      child: FilledButton(
                                        onPressed:
                                            _isBusy ? null : _signInByPhone,
                                        child: Text(
                                          _isBusy
                                              ? 'Signing in...'
                                              : 'Sign in by phone',
                                        ),
                                      ),
                                    ),
                                    if (_showEmailPasswordFallback) ...[
                                      const SizedBox(height: 16),
                                      const Divider(),
                                      const SizedBox(height: 8),
                                      TextField(
                                        controller: _signInEmailController,
                                        keyboardType:
                                            TextInputType.emailAddress,
                                        autofillHints: const <String>[
                                          AutofillHints.email,
                                          AutofillHints.username,
                                        ],
                                        decoration: const InputDecoration(
                                          labelText: 'Email',
                                        ),
                                      ),
                                      const SizedBox(height: 12),
                                      TextField(
                                        controller: _signInPasswordController,
                                        obscureText: true,
                                        autofillHints: const <String>[
                                          AutofillHints.password,
                                        ],
                                        decoration: const InputDecoration(
                                          labelText: 'Password',
                                        ),
                                      ),
                                      const SizedBox(height: 12),
                                      SizedBox(
                                        width: double.infinity,
                                        child: OutlinedButton(
                                          onPressed: _isBusy
                                              ? null
                                              : _signInByEmailPassword,
                                          child: const Text(
                                            'Sign in by email/password',
                                          ),
                                        ),
                                      ),
                                    ],
                                  ],
                                ),
                              ),
                              SingleChildScrollView(
                                child: Column(
                                  children: [
                                    TextField(
                                      controller: _signUpPhoneController,
                                      keyboardType: TextInputType.phone,
                                      autofillHints: const <String>[
                                        AutofillHints.telephoneNumber,
                                      ],
                                      decoration: const InputDecoration(
                                        labelText: 'Phone number *',
                                      ),
                                    ),
                                    const SizedBox(height: 12),
                                    TextField(
                                      controller: _signUpEmailController,
                                      keyboardType: TextInputType.emailAddress,
                                      autofillHints: const <String>[
                                        AutofillHints.email,
                                        AutofillHints.newUsername,
                                      ],
                                      decoration: const InputDecoration(
                                        labelText: 'Email *',
                                      ),
                                    ),
                                    const SizedBox(height: 12),
                                    TextField(
                                      controller: _signUpPasswordController,
                                      obscureText: true,
                                      autofillHints: const <String>[
                                        AutofillHints.newPassword,
                                      ],
                                      decoration: const InputDecoration(
                                        labelText: 'Password *',
                                      ),
                                    ),
                                    const SizedBox(height: 12),
                                    TextField(
                                      controller: _signUpFirstNameController,
                                      decoration: const InputDecoration(
                                        labelText: 'First name (optional)',
                                      ),
                                    ),
                                    const SizedBox(height: 12),
                                    TextField(
                                      controller: _signUpLastNameController,
                                      decoration: const InputDecoration(
                                        labelText: 'Last name (optional)',
                                      ),
                                    ),
                                    const SizedBox(height: 16),
                                    SizedBox(
                                      width: double.infinity,
                                      child: FilledButton(
                                        onPressed: _isBusy ? null : _signUp,
                                        child: Text(
                                          _isBusy
                                              ? 'Signing up...'
                                              : 'Create account',
                                        ),
                                      ),
                                    ),
                                  ],
                                ),
                              ),
                            ],
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class AccountSettingsPage extends StatefulWidget {
  const AccountSettingsPage({
    super.key,
    required this.user,
    required this.authStore,
  });

  final LocalAuthUser user;
  final LocalAuthStore authStore;

  @override
  State<AccountSettingsPage> createState() => _AccountSettingsPageState();
}

class _AccountSettingsPageState extends State<AccountSettingsPage> {
  late final TextEditingController _phoneController;
  late final TextEditingController _passwordController;
  late final TextEditingController _firstNameController;
  late final TextEditingController _lastNameController;
  bool _isSaving = false;

  @override
  void initState() {
    super.initState();
    _phoneController = TextEditingController(text: widget.user.phoneNumber);
    _passwordController = TextEditingController(text: widget.user.password);
    _firstNameController =
        TextEditingController(text: widget.user.firstName ?? '');
    _lastNameController =
        TextEditingController(text: widget.user.lastName ?? '');
  }

  @override
  void dispose() {
    _phoneController.dispose();
    _passwordController.dispose();
    _firstNameController.dispose();
    _lastNameController.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    if (_isSaving) {
      return;
    }
    setState(() {
      _isSaving = true;
    });
    try {
      final updated = await widget.authStore.updateUser(
        input: UpdateProfileInput(
          phoneNumber: _phoneController.text,
          password: _passwordController.text,
          firstName: _firstNameController.text,
          lastName: _lastNameController.text,
        ),
      );
      if (!mounted) {
        return;
      }
      Navigator.of(context).pop(updated);
    } catch (error) {
      if (!mounted) {
        return;
      }
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Profile update failed: $error')),
      );
    } finally {
      if (mounted) {
        setState(() {
          _isSaving = false;
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Update sign in profile')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          TextField(
            controller: _phoneController,
            keyboardType: TextInputType.phone,
            decoration: const InputDecoration(
              labelText: 'Phone number *',
            ),
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _passwordController,
            obscureText: true,
            decoration: const InputDecoration(
              labelText: 'Password *',
            ),
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _firstNameController,
            decoration: const InputDecoration(
              labelText: 'First name',
            ),
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _lastNameController,
            decoration: const InputDecoration(
              labelText: 'Last name',
            ),
          ),
          const SizedBox(height: 20),
          FilledButton(
            onPressed: _isSaving ? null : _save,
            child: Text(_isSaving ? 'Saving...' : 'Save changes'),
          ),
        ],
      ),
    );
  }
}

class ChatHomePage extends StatefulWidget {
  const ChatHomePage({
    super.key,
    required this.cameras,
    required this.logger,
    required this.apiBaseUrl,
    required this.signedInUser,
    required this.authStore,
    required this.onSignedOut,
    required this.onProfileUpdated,
  });

  final List<CameraDescription> cameras;
  final AppLogger logger;
  final String apiBaseUrl;
  final LocalAuthUser signedInUser;
  final LocalAuthStore authStore;
  final VoidCallback onSignedOut;
  final ValueChanged<LocalAuthUser> onProfileUpdated;

  @override
  State<ChatHomePage> createState() => _ChatHomePageState();
}

class _ChatHomePageState extends State<ChatHomePage> {
  static const double _questionTimeoutSeconds = 3600;
  static const double _maxDiscussionMinutes = 60;
  static const double _communicationMinutes = 60;

  final TextEditingController _inputController = TextEditingController();
  final SpeechToText _speechToText = SpeechToText();
  final ScrollController _messagesScrollController = ScrollController();

  late final ApiClient _apiClient;
  late final FileSaver _fileSaver;
  late final List<ChatMessage> _messages;
  ResponderMode _responderMode = ResponderMode.aiUserSimulator;
  late LocaleOption _selectedLocale;
  String? _documentPath;
  bool _isSending = false;
  bool _isDownloading = false;
  bool _hasExportReady = false;
  String _appVersionLabel = 'v0.1.0+1';
  bool _updateDialogShown = false;
  bool _speechEnabled = false;
  bool _isListening = false;
  late LocalAuthUser _signedInUser;

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
    _signedInUser = widget.signedInUser;
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
    _fileSaver = createFileSaver();
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
    unawaited(_loadAppVersion());
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _scrollToLatest(animated: false);
    });
  }

  @override
  void didUpdateWidget(covariant ChatHomePage oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.signedInUser.phoneNumber != widget.signedInUser.phoneNumber ||
        oldWidget.signedInUser.email != widget.signedInUser.email ||
        oldWidget.signedInUser.firstName != widget.signedInUser.firstName ||
        oldWidget.signedInUser.lastName != widget.signedInUser.lastName) {
      _signedInUser = widget.signedInUser;
    }
  }

  Future<void> _loadAppVersion() async {
    try {
      final info = await PackageInfo.fromPlatform();
      if (!mounted) {
        return;
      }
      final version = info.version.trim();
      final build = info.buildNumber.trim();
      final label = build.isEmpty ? 'v$version' : 'v$version+$build';
      final parsed = _SemanticVersion.tryParse(label);
      setState(() {
        _appVersionLabel = label;
      });
      if (parsed != null) {
        unawaited(_checkForGithubUpdate(parsed));
      }
    } catch (_) {}
  }

  Uri _githubLatestReleaseUri() {
    return Uri.parse(
        'https://api.github.com/repos/$_githubOwner/$_githubRepo/releases/latest');
  }

  Future<void> _checkForGithubUpdate(_SemanticVersion installed) async {
    try {
      final response = await http.get(
        _githubLatestReleaseUri(),
        headers: <String, String>{
          'Accept': 'application/vnd.github+json',
          'User-Agent': 'AIJurisDigta-Mobile',
        },
      );
      if (response.statusCode == 404) {
        await widget.logger.info(
          'No GitHub release found for update check',
          <String, Object?>{
            'owner': _githubOwner,
            'repo': _githubRepo,
          },
        );
        return;
      }
      if (response.statusCode < 200 || response.statusCode >= 300) {
        await widget.logger.info(
          'GitHub update check failed',
          <String, Object?>{
            'status_code': response.statusCode,
            'body': response.body,
          },
        );
        return;
      }
      final payload = jsonDecode(response.body) as Map<String, dynamic>;
      if ((payload['draft'] as bool? ?? false) ||
          (payload['prerelease'] as bool? ?? false)) {
        return;
      }
      final tagName = payload['tag_name'] as String? ?? '';
      final releaseUrl = payload['html_url'] as String? ?? '';
      final latestVersion = _SemanticVersion.tryParse(tagName);
      if (latestVersion == null) {
        await widget.logger.info(
          'GitHub release tag is not parseable for app update',
          <String, Object?>{'tag_name': tagName},
        );
        return;
      }
      if (latestVersion.compareTo(installed) <= 0) {
        await widget.logger.info(
          'App is already up to date',
          <String, Object?>{
            'installed': installed.toString(),
            'latest': latestVersion.toString(),
          },
        );
        return;
      }
      if (!mounted || _updateDialogShown) {
        return;
      }
      _updateDialogShown = true;
      await widget.logger.info(
        'New app version available on GitHub',
        <String, Object?>{
          'installed': installed.toString(),
          'latest': latestVersion.toString(),
          'release_url': releaseUrl,
        },
      );
      await _showUpdateDialog(
        installedVersion: installed.toString(),
        latestVersion: latestVersion.toString(),
        releaseUrl: releaseUrl,
      );
    } catch (error, stackTrace) {
      await widget.logger.error(
        'GitHub update check failed',
        error,
        stackTrace,
      );
    }
  }

  Future<void> _showUpdateDialog({
    required String installedVersion,
    required String latestVersion,
    required String releaseUrl,
  }) async {
    if (!mounted) {
      return;
    }
    await showDialog<void>(
      context: context,
      builder: (dialogContext) {
        return AlertDialog(
          title: const Text('Update available'),
          content: Text(
            'A newer version is available on GitHub.\n\nCurrent: $installedVersion\nLatest: $latestVersion',
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(dialogContext).pop(),
              child: const Text('Later'),
            ),
            FilledButton(
              onPressed: () async {
                Navigator.of(dialogContext).pop();
                final uri = Uri.tryParse(releaseUrl);
                if (uri == null) {
                  _showSnackbar('Release URL is invalid.');
                  return;
                }
                final opened = await launchUrl(
                  uri,
                  mode: LaunchMode.platformDefault,
                );
                if (!opened) {
                  _showSnackbar('Could not open update page.');
                }
              },
              child: const Text('Update'),
            ),
          ],
        );
      },
    );
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
    _messagesScrollController.dispose();
    super.dispose();
  }

  void _scrollToLatest({bool animated = true}) {
    if (!_messagesScrollController.hasClients) {
      return;
    }
    final offset = _messagesScrollController.position.maxScrollExtent;
    if (animated) {
      unawaited(
        _messagesScrollController.animateTo(
          offset,
          duration: const Duration(milliseconds: 220),
          curve: Curves.easeOut,
        ),
      );
      return;
    }
    _messagesScrollController.jumpTo(offset);
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
        builder: (_) => CameraCapturePage(
          camera: widget.cameras.first,
          logger: widget.logger,
        ),
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
      _hasExportReady = false;
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
    _scrollToLatest();

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
            _scrollToLatest();
          }
          if (event.event == 'result' || event.event == 'done') {
            if (mounted) {
              setState(() {
                _hasExportReady = true;
              });
            }
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
            _hasExportReady = false;
          });
          _scrollToLatest();
        }
      }
    } on SessionExpiredException {
      _showSnackbar(
        _sessionExpiredMessageForLanguage(_selectedLocale.languageCode),
      );
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

  Future<void> _downloadPdf(String kind) async {
    if (_isDownloading) {
      return;
    }
    if (!_hasExportReady) {
      _showSnackbar(
        'PDF is not ready yet. Complete the AI discussion first.',
      );
      return;
    }
    setState(() {
      _isDownloading = true;
    });
    try {
      await widget.logger.info(
        'PDF export download requested',
        <String, Object?>{'kind': kind, 'session_id': _apiClient.sessionId},
      );
      final payload = await _apiClient.downloadExportPdf(
        kind: kind,
        responderMode: _responderMode,
        locale: _selectedLocale,
      );
      final savedPath = await _fileSaver.save(
        bytes: payload.bytes,
        fileName: payload.filename,
        contentType: payload.contentType,
      );
      await widget.logger.info(
        'PDF export download completed',
        <String, Object?>{
          'kind': kind,
          'filename': payload.filename,
          'saved_path': savedPath,
          'bytes': payload.bytes.length,
        },
      );
      if (savedPath != null && savedPath.isNotEmpty) {
        _showSnackbar('PDF saved to $savedPath');
      } else {
        _showSnackbar('PDF download started: ${payload.filename}');
      }
    } on SessionExpiredException {
      _showSnackbar(
        _sessionExpiredMessageForLanguage(_selectedLocale.languageCode),
      );
    } catch (error, stackTrace) {
      await widget.logger.error(
        'PDF export download failed',
        error,
        stackTrace,
        <String, Object?>{'kind': kind, 'session_id': _apiClient.sessionId},
      );
      _showSnackbar('Failed to download PDF: $error');
    } finally {
      if (mounted) {
        setState(() {
          _isDownloading = false;
        });
      }
    }
  }

  Future<void> _openAccountSettings() async {
    final updated = await Navigator.of(context).push<LocalAuthUser>(
      MaterialPageRoute<LocalAuthUser>(
        builder: (_) => AccountSettingsPage(
          user: _signedInUser,
          authStore: widget.authStore,
        ),
      ),
    );
    if (!mounted || updated == null) {
      return;
    }
    setState(() {
      _signedInUser = updated;
    });
    widget.onProfileUpdated(updated);
    await widget.logger.info(
      'Signed-in profile updated',
      <String, Object?>{
        'phone': updated.phoneNumber,
        'email': updated.email,
      },
    );
  }

  Future<void> _signOut() async {
    _apiClient.resetSession();
    await widget.logger.info(
      'Signed-in user requested sign out',
      <String, Object?>{
        'phone': _signedInUser.phoneNumber,
        'email': _signedInUser.email,
      },
    );
    widget.onSignedOut();
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
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              const Text(
                                'AIJurisDigta',
                                style: TextStyle(
                                  fontSize: 18,
                                  fontWeight: FontWeight.w700,
                                  color: Color(0xFF0A2F6B),
                                ),
                              ),
                              Text(
                                _signedInUser.displayName,
                                style: Theme.of(context)
                                    .textTheme
                                    .labelMedium
                                    ?.copyWith(color: const Color(0xFF234D86)),
                              ),
                              Text(
                                _appVersionLabel,
                                style: Theme.of(context)
                                    .textTheme
                                    .bodySmall
                                    ?.copyWith(color: const Color(0xFF4A628A)),
                              ),
                            ],
                          ),
                        ),
                        FilledButton.tonalIcon(
                          onPressed: _openAccountSettings,
                          icon: const Icon(Icons.manage_accounts),
                          label: const Text('Account'),
                        ),
                        const SizedBox(width: 8),
                        TextButton.icon(
                          onPressed: _signOut,
                          icon: const Icon(Icons.logout),
                          label: const Text('Sign out'),
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
                            widget.logger
                                .info('Attached document path cleared'),
                          );
                        },
                        child: const Text('CLEAR'),
                      ),
                    ],
                  ),
                Expanded(
                  child: Scrollbar(
                    controller: _messagesScrollController,
                    thumbVisibility: true,
                    trackVisibility: true,
                    interactive: true,
                    child: ListView.builder(
                      controller: _messagesScrollController,
                      padding: const EdgeInsets.all(12),
                      itemCount: _messages.length,
                      itemBuilder: (context, index) {
                        final message = _messages[index];
                        final displayContent = _displayContentForMessage(
                          message,
                        );
                        final isUser = message.role == 'user';
                        final speaker = isUser
                            ? 'You'
                            : (message.agentName?.trim().isNotEmpty ?? false)
                                ? message.agentName!
                                : 'Assistant';
                        return Align(
                          alignment: isUser
                              ? Alignment.centerRight
                              : Alignment.centerLeft,
                          child: Container(
                            constraints: const BoxConstraints(maxWidth: 320),
                            margin: const EdgeInsets.only(bottom: 10),
                            padding: const EdgeInsets.all(12),
                            decoration: BoxDecoration(
                              color: isUser
                                  ? Theme.of(context)
                                      .colorScheme
                                      .primaryContainer
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
                                  style:
                                      Theme.of(context).textTheme.labelMedium,
                                ),
                                const SizedBox(height: 4),
                                Text(displayContent),
                                if (message.documentPath != null)
                                  Padding(
                                    padding: const EdgeInsets.only(top: 8),
                                    child: Text(
                                      'Document: ${message.documentPath}',
                                      style:
                                          Theme.of(context).textTheme.bodySmall,
                                    ),
                                  ),
                              ],
                            ),
                          ),
                        );
                      },
                    ),
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
                                    _hasExportReady = false;
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
                                      (locale) =>
                                          DropdownMenuItem<LocaleOption>(
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
                                      _hasExportReady = false;
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
                      FilledButton.tonalIcon(
                        onPressed:
                            (_isDownloading || _isSending || !_hasExportReady)
                                ? null
                                : () => _downloadPdf('summary'),
                        icon: _isDownloading
                            ? const SizedBox(
                                width: 14,
                                height: 14,
                                child:
                                    CircularProgressIndicator(strokeWidth: 2),
                              )
                            : const Icon(Icons.picture_as_pdf),
                        label: const Text('Summary PDF'),
                      ),
                      const SizedBox(width: 8),
                      FilledButton.tonalIcon(
                        onPressed:
                            (_isDownloading || _isSending || !_hasExportReady)
                                ? null
                                : () => _downloadPdf('document'),
                        icon: const Icon(Icons.description),
                        label: const Text('Document PDF'),
                      ),
                    ],
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
  const CameraCapturePage({
    super.key,
    required this.camera,
    required this.logger,
  });

  final CameraDescription camera;
  final AppLogger logger;

  @override
  State<CameraCapturePage> createState() => _CameraCapturePageState();
}

class _CameraCapturePageState extends State<CameraCapturePage> {
  CameraController? _controller;
  Future<void>? _initializeControllerFuture;
  String? _cameraErrorMessage;

  @override
  void initState() {
    super.initState();
    _controller = CameraController(widget.camera, ResolutionPreset.medium);
    _initializeControllerFuture = _initializeCamera();
  }

  Future<void> _initializeCamera() async {
    final controller = _controller;
    if (controller == null) {
      return;
    }

    try {
      await controller.initialize();
    } on CameraException catch (error, stackTrace) {
      await widget.logger.error(
        'Camera initialization failed',
        error,
        stackTrace,
        <String, Object?>{'camera_error_code': error.code},
      );
      final message = _cameraErrorMessageFor(error);
      if (mounted) {
        setState(() {
          _cameraErrorMessage = message;
        });
      }
    } catch (error, stackTrace) {
      await widget.logger.error(
        'Unexpected camera initialization failure',
        error,
        stackTrace,
      );
      if (mounted) {
        setState(() {
          _cameraErrorMessage =
              'Could not initialize camera. Try again or use another device.';
        });
      }
    }
  }

  String _cameraErrorMessageFor(CameraException error) {
    switch (error.code) {
      case 'cameraNotReadable':
        return 'Camera is busy or unavailable. Close other apps using the camera and try again.';
      case 'CameraAccessDenied':
      case 'cameraAccessDenied':
        return 'Camera access was denied. Allow camera permission in the browser and try again.';
      default:
        return 'Could not initialize camera. ${error.description ?? error.code}';
    }
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

    try {
      await _initializeControllerFuture;
      if (_cameraErrorMessage != null) {
        return;
      }
      final image = await controller.takePicture();
      if (mounted) {
        Navigator.of(context).pop(image.path);
      }
    } on CameraException catch (error, stackTrace) {
      await widget.logger.error(
        'Camera capture failed',
        error,
        stackTrace,
        <String, Object?>{'camera_error_code': error.code},
      );
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(_cameraErrorMessageFor(error))),
        );
      }
    } catch (error, stackTrace) {
      await widget.logger.error(
        'Unexpected camera capture failure',
        error,
        stackTrace,
      );
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text(
              'Could not capture the image. Try again or use another device.',
            ),
          ),
        );
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Capture document')),
      body: FutureBuilder<void>(
        future: _initializeControllerFuture,
        builder: (context, snapshot) {
          if (_cameraErrorMessage != null) {
            return Center(
              child: Padding(
                padding: const EdgeInsets.all(24),
                child: Text(
                  _cameraErrorMessage!,
                  textAlign: TextAlign.center,
                ),
              ),
            );
          }

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
              child: Padding(
                padding: const EdgeInsets.all(24),
                child: Text(
                  'Could not initialize camera. ${snapshot.error}',
                  textAlign: TextAlign.center,
                ),
              ),
            );
          }

          return const Center(child: CircularProgressIndicator());
        },
      ),
    );
  }
}
