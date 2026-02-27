import 'dart:convert';

import 'package:camera/camera.dart';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;

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

enum ResponderMode { aiUserSimulator, realPerson }

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

class LocalApiClient {
  LocalApiClient({required this.baseUri});

  final Uri baseUri;

  Future<String> sendMessage({
    required String message,
    required ResponderMode responderMode,
    String? documentPath,
  }) async {
    final payload = <String, Object?>{
      'message': message,
      'mode': responderMode.name,
      'documentPath': documentPath,
    };

    final response = await http.post(
      baseUri.resolve('/chat'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode(payload),
    );

    if (response.statusCode < 200 || response.statusCode >= 300) {
      throw Exception('Local API failed with status ${response.statusCode}.');
    }

    final body = jsonDecode(response.body) as Map<String, dynamic>;
    return body['response'] as String? ?? 'No response message.';
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

  late final LocalApiClient _apiClient;
  ResponderMode _responderMode = ResponderMode.aiUserSimulator;
  String? _documentPath;
  bool _isSending = false;

  @override
  void initState() {
    super.initState();
    _apiClient = LocalApiClient(baseUri: Uri.parse('http://10.0.2.2:8000'));
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
      _showSnackbar('Failed to reach local API: $error');
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
      appBar: AppBar(
        title: const Text('AI Jurisdiction Assistant'),
        actions: [
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 12),
            child: DropdownButtonHideUnderline(
              child: DropdownButton<ResponderMode>(
                value: _responderMode,
                onChanged: (mode) {
                  if (mode == null) {
                    return;
                  }
                  setState(() {
                    _responderMode = mode;
                  });
                },
                items: const [
                  DropdownMenuItem(
                    value: ResponderMode.aiUserSimulator,
                    child: Text('AI User Simulator (default)'),
                  ),
                  DropdownMenuItem(
                    value: ResponderMode.realPerson,
                    child: Text('Real Person'),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
      body: Column(
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
                          : Theme.of(context).colorScheme.surfaceContainerHighest,
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
              child: Row(
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
                            child: CircularProgressIndicator(strokeWidth: 2),
                          )
                        : const Icon(Icons.send),
                    tooltip: 'Send to local API',
                  ),
                ],
              ),
            ),
          ),
        ],
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
