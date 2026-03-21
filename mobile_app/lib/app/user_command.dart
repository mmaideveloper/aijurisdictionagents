import '../auth/local_auth_store.dart';

import 'app_locale.dart';

sealed class UserCommandIntent {
  const UserCommandIntent();
}

class NoopUserCommandIntent extends UserCommandIntent {
  const NoopUserCommandIntent(this.rawText);

  final String rawText;
}

class ChangeLanguageIntent extends UserCommandIntent {
  const ChangeLanguageIntent({required this.locale});

  final LocaleOption locale;
}

class UpdateProfileNameIntent extends UserCommandIntent {
  const UpdateProfileNameIntent({this.firstName, this.lastName});

  final String? firstName;
  final String? lastName;
}

class UserCommandExecutionResult {
  const UserCommandExecutionResult({
    required this.handled,
    this.updatedLocale,
    this.updatedUser,
  });

  final bool handled;
  final LocaleOption? updatedLocale;
  final LocalAuthUser? updatedUser;
}
