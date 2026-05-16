import 'dart:convert';
import 'dart:io';

import 'package:ai_jurisdiction_mobile/chat/intent_mapper.dart';

void main() {
  const mapper = IntentMapper();
  final request = mapper.mapTranscript(
    transcript: 'Over vozidlo BA123AA',
    correlationId: 'demo-correlation-id',
    caseId: 'demo-case-id',
    userId: 'demo-user-id',
    languageCode: 'SK',
  );

  const encoder = JsonEncoder.withIndent('  ');
  stdout.writeln(encoder.convert(request.toJson()));
}
