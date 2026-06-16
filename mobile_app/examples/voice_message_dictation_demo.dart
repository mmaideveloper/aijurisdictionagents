import 'dart:io';

import 'package:ai_jurisdiction_mobile/chat/rule_engine.dart';
import 'package:ai_jurisdiction_mobile/chat/speech_flow.dart';

void main() {
  var draft = mergeRecognizedSpeechDraft(
    existingDraft: '',
    recognizedText: 'Potrebujem poradit so zmluvou',
  );
  draft = mergeRecognizedSpeechDraft(
    existingDraft: draft,
    recognizedText: 'a este s vypovednou lehotou',
    previousRecognizedSegment: draft,
  );

  final finalTranscript = '$draft posli';
  final message = stripTrailingSpokenSendCommand(finalTranscript) ?? draft;

  stdout.writeln('Draft: $draft');
  stdout.writeln(
    'Spoken send recognized: ${hasTrailingSpokenSendCommand(finalTranscript)}',
  );
  stdout.writeln('Message to send: $message');
}
