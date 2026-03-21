import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../app/app_locale.dart';
import '../app/user_command_executor.dart';
import '../app/user_command_parser.dart';
import '../auth/local_auth_store.dart';

class AppLocaleController extends Notifier<LocaleOption> {
  @override
  LocaleOption build() => appLocaleOptions.first;

  void setLocale(LocaleOption locale) {
    state = locale;
  }
}

class SignedInUserController extends Notifier<LocalAuthUser?> {
  @override
  LocalAuthUser? build() => null;

  void setUser(LocalAuthUser? user) {
    state = user;
  }
}

final appLocaleProvider = NotifierProvider<AppLocaleController, LocaleOption>(
  AppLocaleController.new,
);

final signedInUserProvider =
    NotifierProvider<SignedInUserController, LocalAuthUser?>(
  SignedInUserController.new,
);

final userCommandParserProvider = Provider<UserCommandParser>(
  (ref) => const UserCommandParser(),
);

final userCommandExecutorProvider = Provider<UserCommandExecutor>(
  (ref) => UserCommandExecutor(parser: ref.watch(userCommandParserProvider)),
);
