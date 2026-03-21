import '../auth/local_auth_store.dart';
import 'app_locale.dart';
import 'user_command.dart';
import 'user_command_parser.dart';

class UserCommandExecutor {
  const UserCommandExecutor({required UserCommandParser parser})
      : _parser = parser;

  final UserCommandParser _parser;

  Future<UserCommandExecutionResult> execute(
    String rawText, {
    required LocalAuthUser currentUser,
    required List<LocaleOption> locales,
    required LocalAuthStore authStore,
  }) async {
    final intent = _parser.parse(rawText, locales: locales);
    switch (intent) {
      case ChangeLanguageIntent():
        return UserCommandExecutionResult(
          handled: true,
          updatedLocale: intent.locale,
        );
      case UpdateProfileNameIntent():
        final updated = await authStore.updateUser(
          input: UpdateProfileInput(
            phoneNumber: currentUser.phoneNumber,
            password: currentUser.password,
            firstName: intent.firstName ?? currentUser.firstName,
            lastName: intent.lastName ?? currentUser.lastName,
          ),
        );
        return UserCommandExecutionResult(
          handled: true,
          updatedUser: updated,
        );
      case NoopUserCommandIntent():
        return const UserCommandExecutionResult(handled: false);
    }
  }
}
