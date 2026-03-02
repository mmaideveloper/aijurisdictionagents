import 'dart:convert';

import 'package:camera/camera.dart';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:url_launcher/url_launcher.dart';

const String _apiBaseUrl = String.fromEnvironment(
  'AIJ_API_BASE_URL',
  defaultValue: 'http://10.0.2.2:8080',
);
const String _apiKey = String.fromEnvironment(
  'AIJ_API_KEY',
  defaultValue: 'aijuris',
);

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
  LocaleOption(countryCode: 'US', languageCode: 'EN', label: 'United States (EN)'),
];

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final cameras = await availableCameras();
  runApp(AIJurisdictionMobileApp(cameras: cameras));
}

class AIJurisdictionMobileApp extends StatelessWidget {
  const AIJurisdictionMobileApp({super.key, required this.cameras});

  final List<CameraDescription> cameras;

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      debugShowCheckedModeBanner: false,
      title: 'AI Jurisdiction Mobile',
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(seedColor: Colors.indigo),
        useMaterial3: true,
      ),
      home: ChatHomePage(cameras: cameras),
    );
  }
}

class ChatMessage {
  const ChatMessage({
    required this.sender,
    required this.content,
    this.documentPath,
    this.createdAt,
  });

  final String sender;
  final String content;
  final String? documentPath;
  final DateTime? createdAt;
}

class ApiClient {
  ApiClient({required this.baseUri, required this.apiKey});

  final Uri baseUri;
  final String apiKey;
  String? _sessionId;

  String? get sessionId => _sessionId;

  Map<String, String> get _headers => <String, String>{
        'Content-Type': 'application/json',
        'x-api-key': apiKey,
      };

  Future<String> _createSession({
    required ResponderMode responderMode,
    required LocaleOption locale,
  }) async {
    final discussionType = responderMode == ResponderMode.realPerson
        ? 'court'
        : 'advice';
    final sessionResponse = await http.post(
      baseUri.resolve('/v1/chat/sessions'),
      headers: _headers,
      body: jsonEncode(<String, String>{
        'discussion_type': discussionType,
        'country': locale.countryCode,
        'language': locale.languageCode,
      }),
    );

    if (sessionResponse.statusCode < 200 || sessionResponse.statusCode >= 300) {
      throw Exception(
        'Session creation failed with status ${sessionResponse.statusCode}.',
      );
    }

    final body = jsonDecode(sessionResponse.body) as Map<String, dynamic>;
    final sessionId = body['id'] as String?;
    if (sessionId == null || sessionId.isEmpty) {
      throw Exception('Session creation succeeded but no session id was returned.');
    }
    return sessionId;
  }

  Future<String> _ensureSession({
    required ResponderMode responderMode,
    required LocaleOption locale,
  }) async {
    final existing = _sessionId;
    if (existing != null && existing.isNotEmpty) {
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

    final response = await http.post(
      baseUri.resolve('/v1/chat/sessions/$sessionId/reply'),
      headers: _headers,
      body: jsonEncode(payload),
    );

    if (response.statusCode == 404) {
      _sessionId = null;
      final retrySessionId = await _ensureSession(
        responderMode: responderMode,
        locale: locale,
      );
      final retryResponse = await http.post(
        baseUri.resolve('/v1/chat/sessions/$retrySessionId/reply'),
        headers: _headers,
        body: jsonEncode(payload),
      );
      return _parseReply(retryResponse);
    }

    return _parseReply(response);
  }

  Uri exportPdfUrl({required String kind}) {
    final sessionId = _sessionId;
    if (sessionId == null || sessionId.isEmpty) {
      throw Exception('No active session for PDF export.');
    }
    return baseUri.resolve(
      '/v1/chat/sessions/$sessionId/export?format=pdf&kind=$kind',
    );
  }

  String _parseReply(http.Response response) {
    if (response.statusCode < 200 || response.statusCode >= 300) {
      throw Exception('API call failed with status ${response.statusCode}.');
    }

    final body = jsonDecode(response.body) as Map<String, dynamic>;
    return body['content'] as String? ?? 'No response message.';
  }

  void resetSession() {
    _sessionId = null;
  }
}

class ChatHomePage extends StatefulWidget {
  const ChatHomePage({super.key, required this.cameras});

  final List<CameraDescription> cameras;

  @override
  State<ChatHomePage> createState() => _ChatHomePageState();
}

class _ChatHomePageState extends State<ChatHomePage> {
  final TextEditingController _inputController = TextEditingController();
  final List<ChatMessage> _messages = <ChatMessage>[
    const ChatMessage(
      sender: 'assistant',
      content: 'Welcome! Upload a document photo and ask your legal question.',
    ),
  ];

  late final ApiClient _apiClient;
  ResponderMode _responderMode = ResponderMode.aiUserSimulator;
  LocaleOption _selectedLocale = _localeOptions.first;
  String? _documentPath;
  bool _isSending = false;

  @override
  void initState() {
    super.initState();
    _apiClient = ApiClient(baseUri: Uri.parse(_apiBaseUrl), apiKey: _apiKey);
  }

  @override
  void dispose() {
    _inputController.dispose();
    super.dispose();
  }

  Future<void> _captureDocument() async {
    if (widget.cameras.isEmpty) {
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
      _showSnackbar('Document added from camera.');
    }
  }

  Future<void> _sendMessage() async {
    final text = _inputController.text.trim();
    if (text.isEmpty || _isSending) {
      return;
    }

    setState(() {
      _isSending = true;
      _messages.add(
        ChatMessage(
          sender: 'user',
          content: text,
          documentPath: _documentPath,
          createdAt: DateTime.now(),
        ),
      );
    });

    _inputController.clear();

    try {
      final reply = await _apiClient.sendMessage(
        message: text,
        responderMode: _responderMode,
        locale: _selectedLocale,
        documentPath: _documentPath,
      );
      setState(() {
        _messages.add(
          ChatMessage(
            sender: 'assistant',
            content: reply,
            createdAt: DateTime.now(),
          ),
        );
      });
    } catch (error) {
      _showSnackbar('Failed to reach API at $_apiBaseUrl: $error');
    } finally {
      if (mounted) {
        setState(() {
          _isSending = false;
        });
      }
    }
  }

  Future<void> _openPdf(String kind) async {
    try {
      final url = _apiClient.exportPdfUrl(kind: kind);
      final launched = await launchUrl(url, mode: LaunchMode.externalApplication);
      if (!launched && mounted) {
        _showSnackbar('Could not open PDF link: $url');
      }
    } catch (error) {
      _showSnackbar('PDF export unavailable: $error');
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
      appBar: AppBar(title: const Text('AI Jurisdiction Assistant')),
      body: Container(
        decoration: const BoxDecoration(
          gradient: LinearGradient(
            colors: <Color>[Color(0xFFF2F5FF), Color(0xFFE6ECFF), Colors.white],
            begin: Alignment.topCenter,
            end: Alignment.bottomCenter,
          ),
        ),
        child: Stack(
          children: [
            Positioned.fill(
              child: IgnorePointer(
                child: Opacity(
                  opacity: 0.08,
                  child: Center(
                    child: Text(
                      'AIJURISDICTA LOGIN',
                      style: Theme.of(context).textTheme.headlineLarge?.copyWith(
                            fontWeight: FontWeight.w900,
                            letterSpacing: 2.5,
                          ),
                      textAlign: TextAlign.center,
                    ),
                  ),
                ),
              ),
            ),
            Column(
              children: [
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
                      final isUser = message.sender == 'user';
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
                                isUser ? 'You' : 'Assistant',
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
                SafeArea(
                  top: false,
                  child: Padding(
                    padding: const EdgeInsets.fromLTRB(12, 6, 12, 12),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        Row(
                          children: [
                            Expanded(
                              child: DropdownButtonFormField<ResponderMode>(
                                value: _responderMode,
                                decoration: const InputDecoration(
                                  labelText: 'Responder',
                                  border: OutlineInputBorder(),
                                  isDense: true,
                                ),
                                onChanged: (mode) {
                                  if (mode == null) {
                                    return;
                                  }
                                  setState(() {
                                    _responderMode = mode;
                                  });
                                  _apiClient.resetSession();
                                },
                                items: const [
                                  DropdownMenuItem(
                                    value: ResponderMode.aiUserSimulator,
                                    child: Text('AI User Agent'),
                                  ),
                                  DropdownMenuItem(
                                    value: ResponderMode.realPerson,
                                    child: Text('Real User'),
                                  ),
                                ],
                              ),
                            ),
                            const SizedBox(width: 8),
                            Expanded(
                              child: DropdownButtonFormField<LocaleOption>(
                                value: _selectedLocale,
                                decoration: const InputDecoration(
                                  labelText: 'Country / Language',
                                  border: OutlineInputBorder(),
                                  isDense: true,
                                ),
                                onChanged: (locale) {
                                  if (locale == null) {
                                    return;
                                  }
                                  setState(() {
                                    _selectedLocale = locale;
                                  });
                                  _apiClient.resetSession();
                                },
                                items: _localeOptions
                                    .map(
                                      (locale) => DropdownMenuItem<LocaleOption>(
                                        value: locale,
                                        child: Text(locale.label),
                                      ),
                                    )
                                    .toList(growable: false),
                              ),
                            ),
                          ],
                        ),
                        const SizedBox(height: 8),
                        Wrap(
                          spacing: 8,
                          runSpacing: 8,
                          children: [
                            FilledButton.tonalIcon(
                              onPressed: _apiClient.sessionId == null
                                  ? null
                                  : () => _openPdf('summary'),
                              icon: const Icon(Icons.picture_as_pdf),
                              label: const Text('View summary PDF'),
                            ),
                            FilledButton.tonalIcon(
                              onPressed: _apiClient.sessionId == null
                                  ? null
                                  : () => _openPdf('document'),
                              icon: const Icon(Icons.description),
                              label: const Text('View document PDF'),
                            ),
                          ],
                        ),
                        const SizedBox(height: 8),
                        Row(
                          children: [
                            IconButton.filledTonal(
                              onPressed: _captureDocument,
                              icon: const Icon(Icons.document_scanner),
                              tooltip: 'Capture document',
                            ),
                            const SizedBox(width: 8),
                            Expanded(
                              child: TextField(
                                controller: _inputController,
                                minLines: 1,
                                maxLines: 4,
                                textInputAction: TextInputAction.send,
                                onSubmitted: (_) => _sendMessage(),
                                decoration: const InputDecoration(
                                  hintText: 'Ask your legal question...',
                                  border: OutlineInputBorder(),
                                ),
                              ),
                            ),
                            const SizedBox(width: 8),
                            IconButton.filled(
                              onPressed: _isSending ? null : _sendMessage,
                              icon: _isSending
                                  ? const SizedBox(
                                      width: 16,
                                      height: 16,
                                      child: CircularProgressIndicator(
                                        strokeWidth: 2,
                                      ),
                                    )
                                  : const Icon(Icons.send),
                              tooltip: 'Send to API',
                            ),
                          ],
                        ),
                      ],
                    ),
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
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
