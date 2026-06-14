import 'package:ai_jurisdiction_mobile/chat/voice_conversation_settings.dart';

void main() {
  final settings = VoiceConversationSettings.recommended(
    recordChatEnabled: true,
  );
  final encoded = encodeVoiceConversationSettings(settings);
  final decoded = decodeVoiceConversationSettings(encoded);

  print('Record chat enabled: ${decoded.recordChatEnabled}');
  print('User barge-in enabled: ${decoded.allowBargeIn}');
  print('Pause window: ${decoded.pauseFor.inSeconds}s');
  print('Audio retained by app: false');
}
