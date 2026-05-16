import 'package:ai_jurisdiction_mobile/chat/intent_mapper.dart';
import 'package:ai_jurisdiction_mobile/chat/rule_engine.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  const mapper = IntentMapper();

  ToolInvocationRequest map(String transcript, {String languageCode = 'SK'}) {
    return mapper.mapTranscript(
      transcript: transcript,
      correlationId: 'corr-123',
      caseId: 'case-456',
      userId: 'user-789',
      languageCode: languageCode,
      metadata: const <String, Object?>{'client': 'mobile_test'},
    );
  }

  group('IntentMapper', () {
    test('maps Slovak create case transcript to normalized backend payload',
        () {
      final request = map('Vytvor novy pripad s nazvom najomny spor');

      expect(request.toolName, 'create_case');
      expect(request.intent.name, 'create_case');
      expect(request.payload['correlation_id'], 'corr-123');
      expect(request.payload['case_id'], 'case-456');
      expect(request.payload['user_id'], 'user-789');
      expect(request.payload['tool_name'], 'create_case');

      final inputs = request.payload['inputs'] as Map<String, Object?>;
      expect(inputs['title'], 'najomny spor');

      final metadata = request.payload['metadata'] as Map<String, Object?>;
      expect(metadata['source'], 'voice');
      expect(metadata['transcript_preview'],
          'Vytvor novy pripad s nazvom najomny spor');
      expect(metadata['transcript_redacted'], isTrue);
      expect(metadata['transcript_length'], 40);
      expect(metadata['language'], 'SK');
      expect(metadata['client'], 'mobile_test');
    });

    test('maps Slovak repeat create case transcript to title only', () {
      final request = map('Ešte raz vytvor nový prípad test');

      expect(request.toolName, 'create_case');
      final inputs = request.payload['inputs'] as Map<String, Object?>;
      expect(inputs['title'], 'test');
    });

    test('maps English profile and document intents', () {
      final nameRequest = map('Change my name Alex Carter', languageCode: 'EN');
      final documentRequest =
          map('Generate documentation for this case', languageCode: 'EN');
      final emailRequest = map(
        'Send document by email to alex@example.com',
        languageCode: 'EN',
      );

      expect(nameRequest.toolName, 'update_profile_name');
      expect(
        (nameRequest.payload['inputs'] as Map<String, Object?>)['display_name'],
        'Alex Carter',
      );
      expect(documentRequest.toolName, 'generate_documentation');
      expect(emailRequest.toolName, 'send_document_email');
      expect(
        (emailRequest.payload['inputs'] as Map<String, Object?>)['email'],
        'alex@example.com',
      );
    });

    test('maps German verification intents', () {
      final company = map('Unternehmen prufen Muster GmbH', languageCode: 'DE');
      final address = map('Adresse prufen Hauptstrasse 1', languageCode: 'DE');
      final person = map('Person prufen Max Mustermann', languageCode: 'DE');
      final property =
          map('Grundbuch prufen Bratislava 123', languageCode: 'DE');
      final vehicle = map('Fahrzeug prufen BA123AA', languageCode: 'DE');

      expect(company.toolName, 'verify_company');
      expect(address.toolName, 'verify_address');
      expect(person.toolName, 'verify_person');
      expect(property.toolName, 'verify_property_cadastre');
      expect(vehicle.toolName, 'verify_vehicle');
    });

    test('falls back to generic tool request for future tools', () {
      final request = map('Spusti notarizacny workflow pre tento pripad');

      expect(request.toolName, genericToolRequestIntentName);
      expect(request.intent.isFallback, isTrue);
      expect(request.payload['tool_name'], genericToolRequestIntentName);
      expect(request.payload['correlation_id'], 'corr-123');

      final metadata = request.payload['metadata'] as Map<String, Object?>;
      expect(metadata['transcript_preview'],
          'Spusti notarizacny workflow pre tento pripad');
    });

    test('redacts sensitive transcript metadata before send by default', () {
      final request = map(
        'Send document by email to alex@example.com and call +421 900 123 456',
        languageCode: 'EN',
      );

      final metadata = request.payload['metadata'] as Map<String, Object?>;
      expect(
        metadata['transcript_preview'],
        'Send document by email to [redacted-email] and call [redacted-number]',
      );
      expect(metadata['transcript_redacted'], isTrue);
    });

    test('rule engine attaches mapper payload to parsed profile patches', () {
      const engine = RuleEngine();
      final action = engine.evaluate(
        input: 'Zmen adresu na Hlavna 1 Bratislava',
        context: const RuleEngineContext(
          awaitingProfileName: false,
          awaitingCaseArchiveConfirmation: false,
          awaitingCaseTitle: false,
          submitMessageWhenNoRuleMatches: true,
          correlationId: 'corr-123',
          caseId: 'case-456',
          userId: 'user-789',
          languageCode: 'SK',
        ),
      );

      expect(action, isA<RequestProfilePatchRuleAction>());
      final request = (action as RequestProfilePatchRuleAction).toolRequest!;
      expect(request.toolName, 'update_profile_address');
      expect(request.payload['correlation_id'], 'corr-123');
      expect(
        (request.payload['inputs'] as Map<String, Object?>)['address'],
        'Hlavna 1 Bratislava',
      );
    });
  });
}
