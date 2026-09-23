import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:math' as math;
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:record/record.dart';

import '../auth/local_auth_store.dart';

/// Ephemeral native-mobile PCM streaming using the same contract as the website.
class StreamingDictation extends StatefulWidget {
  const StreamingDictation({super.key, required this.baseUrl, required this.apiKey,
    required this.userId, required this.caseId, required this.language,
    required this.authStore, required this.onFinal, required this.onBusy});
  final String baseUrl, apiKey, userId, caseId, language;
  final LocalAuthStore authStore;
  final ValueChanged<String> onFinal;
  final ValueChanged<bool> onBusy;
  @override
  State<StreamingDictation> createState() => StreamingDictationState();
}

class StreamingDictationState extends State<StreamingDictation> with WidgetsBindingObserver {
  final _recorder = AudioRecorder();
  final Map<int, String> _segments = {};
  WebSocket? _socket;
  StreamSubscription<dynamic>? _events;
  StreamSubscription<dynamic>? _audio;
  Timer? _timer;
  Map<String, dynamic>? _route;
  String _state = 'idle', _draft = '';
  int _generation = 0, _seconds = 0;
  double _level = 0;
  bool get _busy => ['permission', 'recording', 'stopping'].contains(_state);
  String _t(String key) {
    const text = {
      'sk': {'start':'Diktovať', 'consent':'Súhlasím — zapnúť mikrofón', 'stop':'Zastaviť', 'cancel':'Zrušiť', 'recording':'Nahrávanie', 'stopping':'Dokončuje sa prepis', 'permission':'Povoľte mikrofón', 'error':'Prepis zlyhal alebo nie je dostupný. Skúste znova alebo správu napíšte.', 'ready':'Skontrolujte prepis a stlačte Odoslať.', 'disclosure':'Zvuk sa odošle na prepis. Aplikácia ho neukladá. Pred odoslaním skontrolujte text.'},
      'en': {'start':'Dictate', 'consent':'I agree — start microphone', 'stop':'Stop', 'cancel':'Cancel', 'recording':'Recording', 'stopping':'Finalizing transcript', 'permission':'Allow microphone access', 'error':'Transcription failed or is unavailable. Retry or type your message.', 'ready':'Review the transcript, then press Send.', 'disclosure':'Audio will be sent for transcription. This app does not save audio. Review the text before sending.'},
      'de': {'start':'Diktieren', 'consent':'Einverstanden — Mikrofon starten', 'stop':'Stoppen', 'cancel':'Abbrechen', 'recording':'Aufnahme', 'stopping':'Transkript wird fertiggestellt', 'permission':'Mikrofonzugriff erlauben', 'error':'Transkription fehlgeschlagen oder nicht verfügbar. Erneut versuchen oder tippen.', 'ready':'Prüfen Sie das Transkript und drücken Sie Senden.', 'disclosure':'Audio wird zur Transkription übertragen. Diese App speichert kein Audio. Prüfen Sie den Text vor dem Senden.'}
    };
    return (text[widget.language] ?? text['en']!)[key] ?? key;
  }
  @override
  void initState() { super.initState(); WidgetsBinding.instance.addObserver(this); }
  @override
  void didUpdateWidget(covariant StreamingDictation oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.caseId != widget.caseId || oldWidget.userId != widget.userId || oldWidget.language != widget.language) {
      unawaited(_cancel());
    }
  }
  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state != AppLifecycleState.resumed) { unawaited(_cancel()); }
  }
  Future<Map<String, String>> _headers() async => {
    'x-api-key': widget.apiKey, ...await widget.authStore.deviceAuthorizationHeaders(),
  };
  Future<void> open() async {
    if (_busy) return;
    final generation = ++_generation;
    setState(() { _state = 'loading'; _draft = ''; });
    try {
      final response = await http.get(Uri.parse('${widget.baseUrl}/v1/speech/cases/${widget.caseId}/route?user_id=${widget.userId}'), headers: await _headers()).timeout(const Duration(seconds: 15));
      if (!mounted || generation != _generation) return;
      if (response.statusCode != 200) throw StateError('route');
      setState(() { _route = jsonDecode(response.body) as Map<String, dynamic>; _state = 'consent'; });
    } catch (_) { if (mounted && generation == _generation) setState(() => _state = 'error'); }
  }
  Future<void> _start() async {
    final generation = ++_generation;
    setState(() { _state = 'permission'; _seconds = 0; _segments.clear(); });
    widget.onBusy(true);
    try {
      if (!await _recorder.hasPermission()) throw StateError('permission');
      if (!mounted || generation != _generation) return;
      final headers = await _headers();
      final base = Uri.parse('${widget.baseUrl}/v1/speech/stream');
      final socket = await WebSocket.connect(base.replace(scheme: base.scheme == 'https' ? 'wss' : 'ws').toString()).timeout(const Duration(seconds: 15));
      if (!mounted || generation != _generation) { await socket.close(); return; }
      _socket = socket;
      _timer = Timer(const Duration(seconds: 20), () => unawaited(_fail()));
      _events = socket.listen((dynamic raw) async {
        if (!mounted || generation != _generation) return;
        try {
          final event = jsonDecode(raw as String) as Map<String, dynamic>;
          if (event['type'] == 'ready') {
            final audio = await _recorder.startStream(const RecordConfig(encoder: AudioEncoder.pcm16bits, sampleRate: 16000, numChannels: 1));
            if (!mounted || generation != _generation) { await _recorder.stop(); return; }
            setState(() => _state = 'recording');
            _timer?.cancel();
            _timer = Timer.periodic(const Duration(seconds: 1), (_) {
              if (!mounted) return;
              setState(() => _seconds++);
              if (_seconds >= 119) unawaited(_stop());
            });
            _audio = audio.listen((bytes) {
              if (generation != _generation) return;
              final pcm = ByteData.sublistView(bytes);
              double power = 0;
              for (var i = 0; i + 1 < bytes.length; i += 2) {
                final sample = pcm.getInt16(i, Endian.little) / 32768;
                power += sample * sample;
              }
              if (bytes.length >= 2) setState(() => _level = (math.sqrt(power / (bytes.length ~/ 2)) * 8).clamp(0, 1));
              for (var offset = 0; offset < bytes.length; offset += 3200) {
                socket.add(bytes.sublist(offset, (offset + 3200).clamp(0, bytes.length)));
              }
            }, onError: (_) => unawaited(_fail()));
          } else if (event['type'] == 'partial' || event['type'] == 'final') {
            final id = event['segment'] as int;
            final words = event['text'] as String;
            if (event['type'] == 'final') _segments.putIfAbsent(id, () => words);
            final visible = Map<int, String>.from(_segments);
            if (!visible.containsKey(id)) visible[id] = words;
            final keys = visible.keys.toList()..sort();
            setState(() => _draft = keys.map((key) => visible[key]!).join('\n'));
          } else if (event['type'] == 'done') {
            widget.onFinal(_draft);
            await _release();
            if (mounted) { setState(() => _state = 'ready'); widget.onBusy(false); }
          } else if (event['type'] == 'error') { await _fail(); }
        } catch (_) { await _fail(); }
      }, onError: (_) { if (generation == _generation) unawaited(_fail()); }, onDone: () { if (generation == _generation && _busy) unawaited(_fail()); });
      socket.add(jsonEncode({'type':'start', 'user_id':widget.userId, 'case_id':widget.caseId,
        'device_id':headers['x-jurisdigta-device-id'], 'device_token':headers['x-jurisdigta-device-token'],
        'api_key':widget.apiKey, 'locale': widget.language == 'sk' ? 'sk-SK' : widget.language == 'de' ? 'de-DE' : 'en-US',
        'consent':true, 'route_revision':_route!['route_revision'], 'format':'pcm_s16le_16000_mono'}));
    } catch (_) { if (generation == _generation) await _fail(); }
  }
  Future<void> _stop() async {
    if (_state != 'recording') return;
    setState(() => _state = 'stopping'); _timer?.cancel();
    try {
      await _recorder.stop(); await _audio?.cancel();
      _socket?.add(jsonEncode({'type':'stop'}));
      _timer = Timer(const Duration(seconds: 20), () => unawaited(_fail()));
    } catch (_) { await _fail(); }
  }
  Future<void> _release() async {
    _generation++; _timer?.cancel();
    final audio = _audio; _audio = null;
    final events = _events; _events = null;
    final socket = _socket; _socket = null;
    try { await events?.cancel(); } catch (_) { /* Continue releasing capture. */ }
    try { await audio?.cancel(); } catch (_) { /* Continue releasing capture. */ }
    try { await _recorder.stop(); } catch (_) { /* Capture may already be stopped. */ }
    try { await socket?.close(); } catch (_) { /* Disconnected transport. */ }
  }
  Future<void> _cancel() async {
    try { _socket?.add(jsonEncode({'type':'cancel'})); } catch (_) { /* Already disconnected. */ }
    await _release();
    if (mounted) { setState(() { _state = 'idle'; _draft = ''; }); widget.onBusy(false); }
  }
  Future<void> _fail() async {
    await _release();
    if (mounted) { setState(() { _state = 'error'; _draft = ''; }); widget.onBusy(false); }
  }
  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this); _generation++; _timer?.cancel();
    unawaited(_audio?.cancel()); unawaited(_events?.cancel()); unawaited(_socket?.close());
    unawaited(_recorder.dispose()); super.dispose();
  }
  @override
  Widget build(BuildContext context) => Padding(padding: const EdgeInsets.all(12), child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
    if (!_busy) TextButton.icon(onPressed: _state == 'loading' ? null : open, icon: const Icon(Icons.mic), label: Text(_t('start'))),
    if (_state == 'consent') ...[
      Text('${_route!['provider']} (${_route!['region']})\n${_t('disclosure')}'),
      TextButton(onPressed: _start, child: Text(_t('consent'))),
      TextButton(onPressed: _cancel, child: Text(_t('cancel'))),
    ],
    if (_busy) ...[
      Semantics(liveRegion: true, child: Text('${_t(_state)} $_seconds s')),
      LinearProgressIndicator(value: _state == 'recording' ? _level : null),
      Wrap(children: [TextButton(onPressed: _state == 'recording' ? _stop : null, child: Text(_t('stop'))), TextButton(onPressed: _cancel, child: Text(_t('cancel')))]),
      if (_draft.isNotEmpty) Text(_draft),
    ],
    if (_state == 'error' || _state == 'ready') Text(_t(_state)),
  ]));
}
