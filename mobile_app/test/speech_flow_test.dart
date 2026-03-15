import 'package:flutter_test/flutter_test.dart';
import 'package:ai_jurisdiction_mobile/chat/speech_flow.dart';

void main() {
  group('speechWelcomeMessage', () {
    test('personalizes the welcome when a stored name exists', () {
      expect(
        speechWelcomeMessage('EN', userName: 'Alex'),
        contains('Alex'),
      );
    });

    test('falls back to the generic welcome without a stored name', () {
      expect(
        speechWelcomeMessage('EN'),
        isNot(contains('{{name}}')),
      );
    });
  });

  group('parseSpokenProfileName', () {
    test('extracts a first and last name from an English phrase', () {
      final parsed = parseSpokenProfileName('my name is Alex Carter');

      expect(parsed, isNotNull);
      expect(parsed!.firstName, 'Alex');
      expect(parsed.lastName, 'Carter');
    });

    test('extracts a first name from a Slovak phrase', () {
      final parsed = parseSpokenProfileName('volam sa Martina');

      expect(parsed, isNotNull);
      expect(parsed!.firstName, 'Martina');
      expect(parsed.lastName, isNull);
    });

    test('rejects a clearly invalid token', () {
      expect(parseSpokenProfileName('12345'), isNull);
    });

    test('rejects a normal sentence while waiting for a name', () {
      expect(
        parseSpokenProfileName('I need help with my tenancy dispute'),
        isNull,
      );
    });
  });
}
