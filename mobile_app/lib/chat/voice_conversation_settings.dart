import 'dart:convert';

const String defaultVoiceConversationSettingsStorageKey =
    'mobile_voice_conversation_settings_v1';

class VoiceSessionStartupState {
  const VoiceSessionStartupState._({
    required this.speakerOutputEnabled,
    required this.speechInputEnabled,
  });

  factory VoiceSessionStartupState.forNewChat(
    VoiceConversationSettings settings,
  ) {
    // Persisted settings configure voice after explicit user activation. They
    // must never activate the microphone or speaker when a chat is opened.
    return const VoiceSessionStartupState._(
      speakerOutputEnabled: false,
      speechInputEnabled: false,
    );
  }

  final bool speakerOutputEnabled;
  final bool speechInputEnabled;
}

class VoiceConversationSettings {
  const VoiceConversationSettings({
    required this.recordChatEnabled,
    required this.allowBargeIn,
    required this.pauseFor,
    required this.listenFor,
    required this.resumeListeningDelay,
  });

  factory VoiceConversationSettings.recommended({
    bool recordChatEnabled = false,
  }) {
    return VoiceConversationSettings(
      recordChatEnabled: recordChatEnabled,
      allowBargeIn: true,
      pauseFor: const Duration(seconds: 45),
      listenFor: const Duration(minutes: 30),
      resumeListeningDelay: const Duration(milliseconds: 150),
    );
  }

  factory VoiceConversationSettings.fromJson(Map<String, Object?> json) {
    return VoiceConversationSettings.recommended(
      recordChatEnabled: json['record_chat_enabled'] == true,
    ).copyWith(
      allowBargeIn: json['allow_barge_in'] as bool?,
      pauseFor: _durationFromSeconds(json['pause_for_seconds']),
      listenFor: _durationFromSeconds(json['listen_for_seconds']),
      resumeListeningDelay:
          _durationFromMilliseconds(json['resume_listening_delay_ms']),
    );
  }

  final bool recordChatEnabled;
  final bool allowBargeIn;
  final Duration pauseFor;
  final Duration listenFor;
  final Duration resumeListeningDelay;

  VoiceConversationSettings copyWith({
    bool? recordChatEnabled,
    bool? allowBargeIn,
    Duration? pauseFor,
    Duration? listenFor,
    Duration? resumeListeningDelay,
  }) {
    return VoiceConversationSettings(
      recordChatEnabled: recordChatEnabled ?? this.recordChatEnabled,
      allowBargeIn: allowBargeIn ?? this.allowBargeIn,
      pauseFor: pauseFor ?? this.pauseFor,
      listenFor: listenFor ?? this.listenFor,
      resumeListeningDelay: resumeListeningDelay ?? this.resumeListeningDelay,
    );
  }

  Map<String, Object?> toJson() {
    return <String, Object?>{
      'record_chat_enabled': recordChatEnabled,
      'allow_barge_in': allowBargeIn,
      'pause_for_seconds': pauseFor.inSeconds,
      'listen_for_seconds': listenFor.inSeconds,
      'resume_listening_delay_ms': resumeListeningDelay.inMilliseconds,
    };
  }

  Map<String, Object?> toLogContext() {
    return <String, Object?>{
      'record_chat_enabled': recordChatEnabled,
      'allow_barge_in': allowBargeIn,
      'pause_for_ms': pauseFor.inMilliseconds,
      'listen_for_ms': listenFor.inMilliseconds,
      'resume_listening_delay_ms': resumeListeningDelay.inMilliseconds,
    };
  }
}

VoiceConversationSettings decodeVoiceConversationSettings(String? rawValue) {
  if (rawValue == null || rawValue.trim().isEmpty) {
    return VoiceConversationSettings.recommended();
  }
  final decoded = jsonDecode(rawValue);
  if (decoded is! Map) {
    return VoiceConversationSettings.recommended();
  }
  return VoiceConversationSettings.fromJson(
    decoded.map<String, Object?>(
      (key, value) => MapEntry(key.toString(), value),
    ),
  );
}

String encodeVoiceConversationSettings(VoiceConversationSettings settings) {
  return jsonEncode(settings.toJson());
}

Duration? _durationFromSeconds(Object? value) {
  if (value is int && value > 0) {
    return Duration(seconds: value);
  }
  return null;
}

Duration? _durationFromMilliseconds(Object? value) {
  if (value is int && value > 0) {
    return Duration(milliseconds: value);
  }
  return null;
}
