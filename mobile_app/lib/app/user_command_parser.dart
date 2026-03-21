import 'app_locale.dart';
import 'user_command.dart';

class UserCommandParser {
  const UserCommandParser();

  UserCommandIntent parse(
    String rawText, {
    required List<LocaleOption> locales,
  }) {
    final normalized = rawText.trim();
    if (normalized.isEmpty) {
      return NoopUserCommandIntent(rawText);
    }

    final languageIntent = _parseLanguageIntent(normalized, locales: locales);
    if (languageIntent != null) {
      return languageIntent;
    }

    final nameIntent = _parseNameIntent(normalized);
    if (nameIntent != null) {
      return nameIntent;
    }

    return NoopUserCommandIntent(rawText);
  }

  ChangeLanguageIntent? _parseLanguageIntent(
    String rawText, {
    required List<LocaleOption> locales,
  }) {
    final lower = rawText.toLowerCase();
    final triggerPatterns = <RegExp>[
      RegExp(r'^(please\s+)?change\s+(the\s+)?language\s+to\s+(.+)$'),
      RegExp(r'^(please\s+)?switch\s+(the\s+)?language\s+to\s+(.+)$'),
      RegExp(r'^(pros[ií]m\s+)?zme[nň]\s+jazyk\s+na\s+(.+)$'),
      RegExp(r'^(pros[ií]m\s+)?prepni\s+jazyk\s+na\s+(.+)$'),
      RegExp(r'^(bitte\s+)?[äa]ndere\s+die\s+sprache\s+zu\s+(.+)$'),
      RegExp(r'^(bitte\s+)?wechsle\s+die\s+sprache\s+zu\s+(.+)$'),
    ];

    for (final pattern in triggerPatterns) {
      final match = pattern.firstMatch(lower);
      if (match == null) {
        continue;
      }
      final target = match.group(match.groupCount)?.trim();
      final locale = _localeForToken(target, locales);
      if (locale != null) {
        return ChangeLanguageIntent(locale: locale);
      }
    }

    return null;
  }

  UpdateProfileNameIntent? _parseNameIntent(String rawText) {
    final lower = rawText.toLowerCase().trim();
    final firstNamePatterns = <RegExp>[
      RegExp(r'^(please\s+)?set\s+my\s+first\s+name\s+to\s+(.+)$'),
      RegExp(r'^(pros[ií]m\s+)?nastav\s+mi\s+meno\s+na\s+(.+)$'),
      RegExp(r'^(bitte\s+)?setze\s+meinen\s+vornamen\s+auf\s+(.+)$'),
    ];
    for (final pattern in firstNamePatterns) {
      final match = pattern.firstMatch(lower);
      if (match != null) {
        final firstName = _titleCaseName(match.group(match.groupCount)!);
        if (firstName.isNotEmpty) {
          return UpdateProfileNameIntent(firstName: firstName);
        }
      }
    }

    final lastNamePatterns = <RegExp>[
      RegExp(r'^(please\s+)?set\s+my\s+last\s+name\s+to\s+(.+)$'),
      RegExp(r'^(pros[ií]m\s+)?nastav\s+mi\s+priezvisko\s+na\s+(.+)$'),
      RegExp(r'^(bitte\s+)?setze\s+meinen\s+nachnamen\s+auf\s+(.+)$'),
    ];
    for (final pattern in lastNamePatterns) {
      final match = pattern.firstMatch(lower);
      if (match != null) {
        final lastName = _titleCaseName(match.group(match.groupCount)!);
        if (lastName.isNotEmpty) {
          return UpdateProfileNameIntent(lastName: lastName);
        }
      }
    }

    final fullNamePatterns = <RegExp>[
      RegExp(r'^(my\s+name\s+is|call\s+me)\s+(.+)$'),
      RegExp(r'^(vol[aá]m\s+sa|som)\s+(.+)$'),
      RegExp(r'^(ich\s+hei[sß]e)\s+(.+)$'),
    ];
    for (final pattern in fullNamePatterns) {
      final match = pattern.firstMatch(lower);
      if (match == null) {
        continue;
      }
      final normalizedName = _titleCaseName(match.group(match.groupCount)!);
      final parts = normalizedName
          .split(RegExp(r'\s+'))
          .where((part) => part.isNotEmpty)
          .toList(growable: false);
      if (parts.isEmpty) {
        return null;
      }
      return UpdateProfileNameIntent(
        firstName: parts.first,
        lastName: parts.length > 1 ? parts.sublist(1).join(' ') : null,
      );
    }

    return null;
  }

  LocaleOption? _localeForToken(String? rawTarget, List<LocaleOption> locales) {
    if (rawTarget == null || rawTarget.isEmpty) {
      return null;
    }
    final target = rawTarget.trim().toLowerCase();
    final aliases = <String, String>{
      'slovak': 'SK',
      'slovensky': 'SK',
      'slovak language': 'SK',
      'english': 'EN',
      'anglicky': 'EN',
      'german': 'DE',
      'deutsch': 'DE',
      'nemecky': 'DE',
      'slovakia': 'SK',
      'united states': 'US',
      'usa': 'US',
      'germany': 'DE',
      'deutschland': 'DE',
      'sk': 'SK',
      'en': 'US',
      'de': 'DE',
      'ge': 'DE',
    };
    final alias = aliases[target] ?? target.toUpperCase();
    for (final locale in locales) {
      if (locale.countryCode == alias ||
          locale.languageCode == alias ||
          locale.label.toLowerCase() == target) {
        return locale;
      }
    }
    return null;
  }

  String _titleCaseName(String rawValue) {
    return rawValue
        .trim()
        .split(RegExp(r'\s+'))
        .where((part) => part.isNotEmpty)
        .map((part) => part[0].toUpperCase() + part.substring(1))
        .join(' ');
  }
}
