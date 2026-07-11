import 'package:ai_jurisdiction_mobile/chat/voice_conversation_settings.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('VoiceConversationSettings', () {
    test('recommended mode keeps audio storage off by app policy', () {
      final settings = VoiceConversationSettings.recommended(
        recordChatEnabled: true,
      );

      expect(settings.recordChatEnabled, isTrue);
      expect(settings.allowBargeIn, isTrue);
      expect(settings.pauseFor, const Duration(seconds: 45));
      expect(settings.listenFor, const Duration(minutes: 30));
      expect(settings.resumeListeningDelay, const Duration(milliseconds: 150));
    });

    test('round-trips persisted JSON', () {
      final settings = VoiceConversationSettings.recommended(
        recordChatEnabled: true,
      ).copyWith(
        pauseFor: const Duration(seconds: 60),
        resumeListeningDelay: const Duration(milliseconds: 250),
      );

      final decoded = decodeVoiceConversationSettings(
        encodeVoiceConversationSettings(settings),
      );

      expect(decoded.recordChatEnabled, isTrue);
      expect(decoded.allowBargeIn, isTrue);
      expect(decoded.pauseFor, const Duration(seconds: 60));
      expect(decoded.listenFor, const Duration(minutes: 30));
      expect(decoded.resumeListeningDelay, const Duration(milliseconds: 250));
    });

    test('falls back to disabled recommended mode for empty values', () {
      final decoded = decodeVoiceConversationSettings('');

      expect(decoded.recordChatEnabled, isFalse);
      expect(decoded.allowBargeIn, isTrue);
      expect(decoded.pauseFor, const Duration(seconds: 45));
    });

    test('new chat waits for explicit voice activation', () {
      final persistedSettings = VoiceConversationSettings.recommended(
        recordChatEnabled: true,
      );

      final startupState =
          VoiceSessionStartupState.forNewChat(persistedSettings);

      expect(persistedSettings.recordChatEnabled, isTrue);
      expect(startupState.speakerOutputEnabled, isFalse);
      expect(startupState.speechInputEnabled, isFalse);
    });
  });
}
