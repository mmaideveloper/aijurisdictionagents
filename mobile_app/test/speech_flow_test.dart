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

  group('speechInputReadyMessage', () {
    test('uses the first name when available', () {
      expect(
        speechInputReadyMessage('EN', firstName: 'Martin'),
        'Hello, Martin, I am listening.',
      );
    });

    test('falls back to a generic listening prompt', () {
      expect(
        speechInputReadyMessage('EN'),
        'Hello, I am listening.',
      );
    });

    test('localizes the listening prompt for Slovak', () {
      expect(
        speechInputReadyMessage('SK', firstName: 'Martin'),
        'Ahoj, Martin, pocuvam vas.',
      );
    });
  });

  group('parseSpokenCaseCreationCommand', () {
    test('extracts a case title from an English command', () {
      final parsed = parseSpokenCaseCreationCommand(
        'Create a new case with name Tenant dispute',
      );

      expect(parsed, isNotNull);
      expect(parsed!.title, 'Tenant dispute');
      expect(parsed.requiresTitlePrompt, isFalse);
    });

    test('extracts a case title from a Slovak command', () {
      final parsed = parseSpokenCaseCreationCommand(
        'Vytvor novy pripad s nazvom Spor so susedom',
      );

      expect(parsed, isNotNull);
      expect(parsed!.title, 'Spor so susedom');
      expect(parsed.requiresTitlePrompt, isFalse);
    });

    test('extracts a case title from a mixed Slovak command with case word',
        () {
      final parsed = parseSpokenCaseCreationCommand(
        'Vytvor mi novy case s nazvom splnomocnenie',
      );

      expect(parsed, isNotNull);
      expect(parsed!.title, 'splnomocnenie');
      expect(parsed.requiresTitlePrompt, isFalse);
    });

    test('extracts a case title from a German command', () {
      final parsed = parseSpokenCaseCreationCommand(
        'Erstelle einen neuen Fall mit Namen Mietstreit',
      );

      expect(parsed, isNotNull);
      expect(parsed!.title, 'Mietstreit');
      expect(parsed.requiresTitlePrompt, isFalse);
    });

    test('requests a prompt when no case title was spoken', () {
      final parsed = parseSpokenCaseCreationCommand('Create a new case');

      expect(parsed, isNotNull);
      expect(parsed!.title, isNull);
      expect(parsed.requiresTitlePrompt, isTrue);
    });
  });

  group('isSpokenSendCommand', () {
    test('matches English send command', () {
      expect(isSpokenSendCommand('Send'), isTrue);
      expect(isSpokenSendCommand('please send message'), isTrue);
    });

    test('matches Slovak send command', () {
      expect(isSpokenSendCommand('Prosim odosli spravu'), isTrue);
      expect(isSpokenSendCommand('Posli'), isTrue);
    });

    test('matches German send command', () {
      expect(isSpokenSendCommand('Bitte senden'), isTrue);
      expect(isSpokenSendCommand('Nachricht senden'), isTrue);
    });

    test('does not match normal dictated content', () {
      expect(isSpokenSendCommand('I need help with my contract'), isFalse);
    });
  });

  group('generateCaseTitleFromDiscussion', () {
    test('builds a meaningful English title', () {
      expect(
        generateCaseTitleFromDiscussion(
          'I need help with tenancy dispute and unpaid rent',
          languageCode: 'EN',
        ),
        'Tenancy dispute unpaid rent',
      );
    });

    test('builds a meaningful Slovak title', () {
      expect(
        generateCaseTitleFromDiscussion(
          'Potrebujem pomoc so splnomocnenim pre predaj auta',
          languageCode: 'SK',
        ),
        'Pomoc splnomocnenim predaj auta',
      );
    });

    test('falls back when no meaningful words exist', () {
      expect(
        generateCaseTitleFromDiscussion('a a a', languageCode: 'EN'),
        'New case',
      );
    });
  });
}
