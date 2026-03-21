import 'package:ai_jurisdiction_mobile/app/app_locale.dart';
import 'package:ai_jurisdiction_mobile/app/user_command.dart';
import 'package:ai_jurisdiction_mobile/app/user_command_parser.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  const parser = UserCommandParser();

  test('parses language change command', () {
    final intent = parser.parse(
      'change language to english',
      locales: appLocaleOptions,
    );

    expect(intent, isA<ChangeLanguageIntent>());
    expect((intent as ChangeLanguageIntent).locale.languageCode, 'EN');
  });

  test('parses full name command', () {
    final intent = parser.parse(
      'my name is jane doe',
      locales: appLocaleOptions,
    );

    expect(intent, isA<UpdateProfileNameIntent>());
    expect((intent as UpdateProfileNameIntent).firstName, 'Jane');
    expect(intent.lastName, 'Doe');
  });
}
