import 'dart:io';

import 'package:ai_jurisdiction_mobile/app/app_locale.dart';
import 'package:ai_jurisdiction_mobile/app/user_command.dart';
import 'package:ai_jurisdiction_mobile/state/mobile_app_providers.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

void main() {
  final container = ProviderContainer();
  final parser = container.read(userCommandParserProvider);
  final localeController = container.read(appLocaleProvider.notifier);

  final parsed = parser.parse(
    'change language to english',
    locales: appLocaleOptions,
  );
  if (parsed is ChangeLanguageIntent) {
    localeController.setLocale(parsed.locale);
  }

  final selected = container.read(appLocaleProvider);
  stdout.writeln(
    'Selected locale: ${selected.countryCode}/${selected.languageCode}',
  );

  container.dispose();
}
