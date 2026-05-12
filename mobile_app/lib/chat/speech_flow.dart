import 'rule_engine.dart';

const Map<String, String> _welcomeMessagesByLanguage = <String, String>{
  'SK':
      'Ahoj, som Jurisdicta. Pomôžem vám s vaším prípadom. Popíšte svoj problém a nahrajte relevantnú dokumentáciu.',
  'EN':
      'Hello, I am Jurisdicta. I can help you with your case. Please describe your problem and upload relevant documentation.',
  'GE':
      'Hallo, ich bin Jurisdicta. Ich kann Ihnen bei Ihrem Fall helfen. Bitte beschreiben Sie Ihr Problem und laden Sie relevante Unterlagen hoch.',
};

const Map<String, String> _namedWelcomeMessagesByLanguage = <String, String>{
  'SK':
      'Ahoj, {{name}}, som Jurisdicta. Pomôžem vám s vaším prípadom. Popíšte svoj problém a nahrajte relevantnú dokumentáciu.',
  'EN':
      'Hello, {{name}}, I am Jurisdicta. I can help you with your case. Please describe your problem and upload relevant documentation.',
  'GE':
      'Hallo, {{name}}, ich bin Jurisdicta. Ich kann Ihnen bei Ihrem Fall helfen. Bitte beschreiben Sie Ihr Problem und laden Sie relevante Unterlagen hoch.',
};

const Map<String, String> _namePromptMessagesByLanguage = <String, String>{
  'SK':
      'Ahoj, som Jurisdicta. Pred spustením hlasového toku mi prosím povedzte, ako vás mám oslovovať.',
  'EN':
      'Hello, I am Jurisdicta. Before we start the speech flow, please tell me what I should call you.',
  'GE':
      'Hallo, ich bin Jurisdicta. Bevor wir mit dem Sprachablauf beginnen, sagen Sie mir bitte, wie ich Sie ansprechen soll.',
};

const Map<String, String> _nameSavedMessagesByLanguage = <String, String>{
  'SK':
      'Teší ma, {{name}}. Vaše meno som uložila do profilu. Teraz môžete nadiktovať svoju otázku.',
  'EN':
      'Nice to meet you, {{name}}. I saved your name to your profile. You can dictate your question now.',
  'GE':
      'Freut mich, {{name}}. Ich habe Ihren Namen in Ihrem Profil gespeichert. Sie können jetzt Ihre Frage diktieren.',
};

const Map<String, String> _nameRetryMessagesByLanguage = <String, String>{
  'SK':
      'Nezachytila som meno dostatočne presne. Prosím, povedzte iba svoje meno alebo meno a priezvisko.',
  'EN':
      'I did not catch the name clearly enough. Please say only your first name or your first and last name.',
  'GE':
      'Ich habe den Namen nicht klar genug verstanden. Bitte sagen Sie nur Ihren Vornamen oder Vor- und Nachnamen.',
};

const Map<String, String> _inputReadyMessagesByLanguage = <String, String>{
  'SK': 'Ahoj{{name_part}}, počúvam vás. Ak chcete dokončiť, povedzte „To je všetko“ alebo kliknite na Odoslať.',
  'EN': 'Hello{{name_part}}, I am listening. To finish, say “I am done” or tap Send.',
  'GE': 'Hallo{{name_part}}, ich höre zu. Zum Beenden sagen Sie „Alles“ oder tippen Sie auf Senden.',
};

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
        _namedWelcomeMessagesByLanguage['SK']!;
    return template.replaceAll('{{name}}', resolvedName);
  }
  return _welcomeMessagesByLanguage[normalized] ??
      _welcomeMessagesByLanguage['SK']!;
}

String speechNamePromptMessage(String languageCode) {
  final normalized = normalizeSpeechLanguageCode(languageCode);
  return _namePromptMessagesByLanguage[normalized] ??
      _namePromptMessagesByLanguage['SK']!;
}

String speechNameSavedMessage(String languageCode, {required String userName}) {
  final normalized = normalizeSpeechLanguageCode(languageCode);
  final template = _nameSavedMessagesByLanguage[normalized] ??
      _nameSavedMessagesByLanguage['SK']!;
  return template.replaceAll('{{name}}', userName.trim());
}

String speechNameRetryMessage(String languageCode) {
  final normalized = normalizeSpeechLanguageCode(languageCode);
  return _nameRetryMessagesByLanguage[normalized] ??
      _nameRetryMessagesByLanguage['SK']!;
}

String speechInputReadyMessage(String languageCode, {String? firstName}) {
  final normalized = normalizeSpeechLanguageCode(languageCode);
  final resolvedFirstName = (firstName ?? '').trim();
  final template = _inputReadyMessagesByLanguage[normalized] ??
      _inputReadyMessagesByLanguage['SK']!;
  final namePart = resolvedFirstName.isEmpty ? '' : ', $resolvedFirstName';
  return template.replaceAll('{{name_part}}', namePart);
}
