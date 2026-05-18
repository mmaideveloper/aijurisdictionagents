import 'package:ai_jurisdiction_mobile/auth/local_auth_store.dart';
import 'package:ai_jurisdiction_mobile/chat/profile_service.dart';
import 'package:ai_jurisdiction_mobile/chat/rule_engine.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('parseSpokenProfilePatchCommand', () {
    test('parses Slovak first name update', () {
      final patch = parseSpokenProfilePatchCommand('zmeň meno na Martina');

      expect(patch, isNotNull);
      expect(patch!.field, ProfilePatchField.firstName);
      expect(patch.value, 'Martina');
    });

    test('parses English last name update', () {
      final patch = parseSpokenProfilePatchCommand(
        'change my last name to Novak',
      );

      expect(patch, isNotNull);
      expect(patch!.field, ProfilePatchField.lastName);
      expect(patch.value, 'Novak');
    });

    test('parses German address update', () {
      final patch = parseSpokenProfilePatchCommand(
        'ändere meine Adresse zu Hauptstrasse 12',
      );

      expect(patch, isNotNull);
      expect(patch!.field, ProfilePatchField.address);
      expect(patch.value, 'Hauptstrasse 12');
    });

    test('normalizes and validates address values', () {
      expect(
        normalizeProfileAddress('  Hlavná   12 ,  Bratislava  '),
        'Hlavná 12, Bratislava',
      );
      expect(normalizeProfileAddress('A 1'), isNull);
      expect(normalizeProfileAddress('Main <script>'), isNull);
    });
  });

  group('RuleEngine profile patch flow', () {
    const engine = RuleEngine();

    test('routes a profile patch request before normal message submission', () {
      final action = engine.evaluate(
        input: 'change address to Main Street 12',
        context: const RuleEngineContext(
          awaitingProfileName: false,
          awaitingCaseArchiveConfirmation: false,
          awaitingCaseTitle: false,
          submitMessageWhenNoRuleMatches: true,
        ),
      );

      expect(action, isA<RequestProfilePatchRuleAction>());
      final patch = (action as RequestProfilePatchRuleAction).patch;
      expect(patch?.field, ProfilePatchField.address);
      expect(patch?.value, 'Main Street 12');
    });

    test('requires explicit confirmation for a pending profile patch', () {
      const pending = SpokenProfilePatch(
        field: ProfilePatchField.firstName,
        value: 'Alex',
      );
      final action = engine.evaluate(
        input: 'yes',
        context: const RuleEngineContext(
          awaitingProfileName: false,
          awaitingProfilePatchConfirmation: true,
          pendingProfilePatch: pending,
          awaitingCaseArchiveConfirmation: false,
          awaitingCaseTitle: false,
          submitMessageWhenNoRuleMatches: true,
        ),
      );

      expect(action, isA<ConfirmProfilePatchRuleAction>());
      final confirmationAction = action as ConfirmProfilePatchRuleAction;
      expect(confirmationAction.confirmation, SpokenConfirmationChoice.yes);
      expect(confirmationAction.patch, same(pending));
    });

    test('accepts German cancellation for a pending profile patch', () {
      final action = engine.evaluate(
        input: 'nein',
        context: const RuleEngineContext(
          awaitingProfileName: false,
          awaitingProfilePatchConfirmation: true,
          pendingProfilePatch: SpokenProfilePatch(
            field: ProfilePatchField.address,
            value: 'Hauptstrasse 12',
          ),
          awaitingCaseArchiveConfirmation: false,
          awaitingCaseTitle: false,
          submitMessageWhenNoRuleMatches: true,
        ),
      );

      expect(action, isA<ConfirmProfilePatchRuleAction>());
      expect(
        (action as ConfirmProfilePatchRuleAction).confirmation,
        SpokenConfirmationChoice.no,
      );
    });
  });

  group('ProfileService', () {
    test('sends PATCH input with voice audit payload', () async {
      UpdateProfileInput? capturedInput;
      final service = ProfileService(
        clock: () => DateTime.utc(2026, 5, 15, 10, 30),
        patchTransport: (input) async {
          capturedInput = input;
          return const LocalAuthUser(
            userId: 'user-1',
            phoneNumber: '+421900000001',
            email: 'alex@example.com',
            password: 'secret',
            firstName: 'Alex',
            lastName: 'Novak',
            address: 'Main Street 12',
          );
        },
      );

      await service.patchProfileFromVoice(
        currentUser: const LocalAuthUser(
          userId: 'user-1',
          phoneNumber: '+421900000001',
          email: 'alex@example.com',
          password: 'secret',
          firstName: 'Alex',
          lastName: 'Old',
          address: 'Old Street 1',
        ),
        patch: const SpokenProfilePatch(
          field: ProfilePatchField.address,
          value: 'Main Street 12',
        ),
        requestedBy: 'user-1',
      );

      expect(capturedInput, isNotNull);
      expect(capturedInput!.address, 'Main Street 12');
      expect(capturedInput!.firstName, 'Alex');
      expect(capturedInput!.lastName, 'Old');
      expect(capturedInput!.auditPayload, <String, Object?>{
        'requested_by': 'user-1',
        'changed_field': 'address',
        'previous_value': 'Old Street 1',
        'new_value': 'Main Street 12',
        'timestamp': '2026-05-15T10:30:00.000Z',
        'source': 'voice',
      });
    });
  });
}
