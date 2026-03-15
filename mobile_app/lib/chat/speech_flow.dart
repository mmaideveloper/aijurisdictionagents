class SpokenProfileName {
  const SpokenProfileName({
    required this.firstName,
    this.lastName,
  });

  final String firstName;
  final String? lastName;

  String get displayName {
    final last = (lastName ?? '').trim();
    if (last.isEmpty) {
      return firstName;
    }
    return '$firstName $last';
  }
}

const String _fallbackLanguageCode = 'SK';

const Map<String, String> _welcomeMessagesByLanguage = <String, String>{
  'SK':
      'Ahoj, som Jurisdicta. Pomozem vam s vasim pripadom. Popiste svoj problem a nahrajte relevantnu dokumentaciu.',
  'EN':
      'Hello, I am Jurisdicta. I can help you with your case. Please describe your problem and upload relevant documentation.',
  'GE':
      'Hallo, ich bin Jurisdicta. Ich kann Ihnen bei Ihrem Fall helfen. Bitte beschreiben Sie Ihr Problem und laden Sie relevante Unterlagen hoch.',
};

const Map<String, String> _namedWelcomeMessagesByLanguage = <String, String>{
  'SK':
      'Ahoj, {{name}}, som Jurisdicta. Pomozem vam s vasim pripadom. Popiste svoj problem a nahrajte relevantnu dokumentaciu.',
  'EN':
      'Hello, {{name}}, I am Jurisdicta. I can help you with your case. Please describe your problem and upload relevant documentation.',
  'GE':
      'Hallo, {{name}}, ich bin Jurisdicta. Ich kann Ihnen bei Ihrem Fall helfen. Bitte beschreiben Sie Ihr Problem und laden Sie relevante Unterlagen hoch.',
};

const Map<String, String> _namePromptMessagesByLanguage = <String, String>{
  'SK':
      'Ahoj, som Jurisdicta. Pred spustenim hlasoveho toku mi prosim povedzte, ako vas mam oslovovat.',
  'EN':
      'Hello, I am Jurisdicta. Before we start the speech flow, please tell me what I should call you.',
  'GE':
      'Hallo, ich bin Jurisdicta. Bevor wir mit dem Sprachablauf beginnen, sagen Sie mir bitte, wie ich Sie ansprechen soll.',
};

const Map<String, String> _nameSavedMessagesByLanguage = <String, String>{
  'SK':
      'Tesim ma, {{name}}. Vase meno som ulozila do profilu. Teraz mozete nadiktovat svoju otazku.',
  'EN':
      'Nice to meet you, {{name}}. I saved your name to your profile. You can dictate your question now.',
  'GE':
      'Freut mich, {{name}}. Ich habe Ihren Namen in Ihrem Profil gespeichert. Sie koennen jetzt Ihre Frage diktieren.',
};

const Map<String, String> _nameRetryMessagesByLanguage = <String, String>{
  'SK':
      'Nezachytila som meno dostatocne presne. Prosim, povedzte iba svoje meno alebo meno a priezvisko.',
  'EN':
      'I did not catch the name clearly enough. Please say only your first name or your first and last name.',
  'GE':
      'Ich habe den Namen nicht klar genug verstanden. Bitte sagen Sie nur Ihren Vornamen oder Vor- und Nachnamen.',
};

String normalizeSpeechLanguageCode(String languageCode) {
  final normalized = languageCode.trim().toUpperCase();
  if (normalized == 'DE') {
    return 'GE';
  }
  switch (normalized) {
    case 'SK':
    case 'EN':
    case 'GE':
      return normalized;
    default:
      return _fallbackLanguageCode;
  }
}

String? resolveStoredProfileName({
  String? firstName,
  String? lastName,
}) {
  final first = (firstName ?? '').trim();
  final last = (lastName ?? '').trim();
  final joined = '$first $last'.trim();
  if (joined.isEmpty) {
    return null;
  }
  return joined;
}

String speechWelcomeMessage(String languageCode, {String? userName}) {
  final normalized = normalizeSpeechLanguageCode(languageCode);
  final resolvedName = (userName ?? '').trim();
  if (resolvedName.isNotEmpty) {
    final template = _namedWelcomeMessagesByLanguage[normalized] ??
        _namedWelcomeMessagesByLanguage[_fallbackLanguageCode]!;
    return template.replaceAll('{{name}}', resolvedName);
  }
  return _welcomeMessagesByLanguage[normalized] ??
      _welcomeMessagesByLanguage[_fallbackLanguageCode]!;
}

String speechNamePromptMessage(String languageCode) {
  final normalized = normalizeSpeechLanguageCode(languageCode);
  return _namePromptMessagesByLanguage[normalized] ??
      _namePromptMessagesByLanguage[_fallbackLanguageCode]!;
}

String speechNameSavedMessage(String languageCode, {required String userName}) {
  final normalized = normalizeSpeechLanguageCode(languageCode);
  final template = _nameSavedMessagesByLanguage[normalized] ??
      _nameSavedMessagesByLanguage[_fallbackLanguageCode]!;
  return template.replaceAll('{{name}}', userName.trim());
}

String speechNameRetryMessage(String languageCode) {
  final normalized = normalizeSpeechLanguageCode(languageCode);
  return _nameRetryMessagesByLanguage[normalized] ??
      _nameRetryMessagesByLanguage[_fallbackLanguageCode]!;
}

SpokenProfileName? parseSpokenProfileName(String spokenText) {
  var normalized = spokenText.trim();
  if (normalized.isEmpty) {
    return null;
  }

  normalized = normalized.replaceAll(RegExp(r'[.,!?;:"()]'), ' ');
  final lowered = normalized.toLowerCase();
  const leadingPhrases = <String>[
    'my name is ',
    'i am ',
    "i'm ",
    'call me ',
    'this is ',
    'volam sa ',
    'moje meno je ',
    'som ',
    'mein name ist ',
    'ich bin ',
    'nenn mich ',
  ];

  for (final phrase in leadingPhrases) {
    if (lowered.startsWith(phrase)) {
      normalized = normalized.substring(phrase.length).trim();
      break;
    }
  }

  final tokens = normalized
      .split(RegExp(r'\s+'))
      .map(_sanitizeNameToken)
      .where((token) => token.isNotEmpty)
      .toList(growable: false);
  if (tokens.isEmpty) {
    return null;
  }
  if (tokens.length > 3) {
    return null;
  }
  if (_isClearlyInvalidNameToken(tokens.first)) {
    return null;
  }

  final firstName = tokens.first;
  String? lastName;
  if (tokens.length > 1) {
    final tail = tokens.sublist(1);
    if (tail.any(_isClearlyInvalidNameToken)) {
      return null;
    }
    lastName = tail.join(' ');
  }

  return SpokenProfileName(
    firstName: firstName,
    lastName: lastName,
  );
}

String _sanitizeNameToken(String token) {
  var value = token.trim();
  const edgeCharacters = ' \t\r\n-_,.?!;:"\'`()[]{}';
  while (value.isNotEmpty && edgeCharacters.contains(value[0])) {
    value = value.substring(1);
  }
  while (value.isNotEmpty && edgeCharacters.contains(value[value.length - 1])) {
    value = value.substring(0, value.length - 1);
  }
  return value;
}

bool _isClearlyInvalidNameToken(String token) {
  if (token.isEmpty) {
    return true;
  }
  return RegExp(r'^\d+$').hasMatch(token);
}
