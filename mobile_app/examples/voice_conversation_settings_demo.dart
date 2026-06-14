import 'dart:io';

import 'package:ai_jurisdiction_mobile/chat/voice_conversation_settings.dart';

void main() {
  final settings = VoiceConversationSettings.recommended(
    recordChatEnabled: true,
  );
  final encoded = encodeVoiceConversationSettings(settings);
  final decoded = decodeVoiceConversationSettings(encoded);

  stdout.writeln('Record chat enabled: ${decoded.recordChatEnabled}');
  stdout.writeln('User barge-in enabled: ${decoded.allowBargeIn}');
  stdout.writeln('Pause window: ${decoded.pauseFor.inSeconds}s');
  stdout.writeln('Audio retained by app: false');
}
