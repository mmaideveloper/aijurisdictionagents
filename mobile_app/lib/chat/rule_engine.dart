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

class SpokenCaseCreationCommand {
  const SpokenCaseCreationCommand({
    required this.title,
  });

  final String? title;

  bool get requiresTitlePrompt => title == null || title!.trim().isEmpty;
}

enum SpokenConfirmationChoice { yes, no }

class RuleEngineContext {
  const RuleEngineContext({
    required this.awaitingProfileName,
    required this.awaitingCaseArchiveConfirmation,
    required this.awaitingCaseTitle,
    required this.submitMessageWhenNoRuleMatches,
    this.currentDraft,
    this.lastDictatedDraft,
  });

  final bool awaitingProfileName;
  final bool awaitingCaseArchiveConfirmation;
  final bool awaitingCaseTitle;
  final bool submitMessageWhenNoRuleMatches;
  final String? currentDraft;
  final String? lastDictatedDraft;
}

sealed class RuleEngineAction {
  const RuleEngineAction();
}

class IgnoreRuleAction extends RuleEngineAction {
  const IgnoreRuleAction();
}

class StoreProfileNameRuleAction extends RuleEngineAction {
  const StoreProfileNameRuleAction({
    required this.profileName,
  });

  final SpokenProfileName? profileName;
}

class ConfirmCaseArchiveRuleAction extends RuleEngineAction {
  const ConfirmCaseArchiveRuleAction({
    required this.confirmation,
  });

  final SpokenConfirmationChoice? confirmation;
}

class CreateCaseRuleAction extends RuleEngineAction {
  const CreateCaseRuleAction({
    required this.title,
  });

  final String? title;

  bool get requiresTitlePrompt => title == null || title!.trim().isEmpty;
}

class SendCurrentDraftRuleAction extends RuleEngineAction {
  const SendCurrentDraftRuleAction({
    required this.message,
  });

  final String message;
}

class SubmitMessageRuleAction extends RuleEngineAction {
  const SubmitMessageRuleAction({
    required this.message,
  });

  final String message;
}

class RuleEngine {
  const RuleEngine();

  RuleEngineAction evaluate({
    required String input,
    required RuleEngineContext context,
  }) {
    final normalizedText = input.trim();
    if (normalizedText.isEmpty) {
      return const IgnoreRuleAction();
    }

    if (context.awaitingCaseArchiveConfirmation) {
      return ConfirmCaseArchiveRuleAction(
        confirmation: parseSpokenConfirmation(normalizedText),
      );
    }

    if (context.awaitingCaseTitle) {
      return CreateCaseRuleAction(title: normalizedText);
    }

    if (context.awaitingProfileName) {
      return StoreProfileNameRuleAction(
        profileName: parseSpokenProfileName(normalizedText),
      );
    }

    if (isSpokenSendCommand(normalizedText)) {
      final pendingMessage = resolvePendingMessageForSendCommand(
        commandText: normalizedText,
        currentDraft: context.currentDraft,
        lastDictatedDraft: context.lastDictatedDraft,
      );
      if (pendingMessage == null) {
        return const IgnoreRuleAction();
      }
      return SendCurrentDraftRuleAction(message: pendingMessage);
    }

    final caseCommand = parseSpokenCaseCreationCommand(normalizedText);
    if (caseCommand != null) {
      return CreateCaseRuleAction(title: caseCommand.title);
    }

    if (!context.submitMessageWhenNoRuleMatches) {
      return const IgnoreRuleAction();
    }

    return SubmitMessageRuleAction(message: normalizedText);
  }
}

bool isSpokenSendCommand(String spokenText) {
  final tokens = _tokenizeSpeechCommand(spokenText);
  if (tokens.isEmpty) {
    return false;
  }
  final normalized =
      tokens.map(_normalizeSpeechCommandToken).toList(growable: false);
  final filtered = normalized
      .skip(_skipLeadingPolitePrefixes(normalized))
      .toList(growable: false);
  if (filtered.isEmpty) {
    return false;
  }
  return _sendCommandPatterns
      .any((pattern) => _matchesExactPattern(filtered, pattern));
}

const String _fallbackLanguageCode = 'SK';

const Set<String> _sendCommandPolitePrefixes = <String>{
  'please',
  'prosim',
  'bitte',
};

const List<List<String>> _sendCommandPatterns = <List<String>>[
  <String>['send'],
  <String>['send', 'it'],
  <String>['send', 'message'],
  <String>['submit'],
  <String>['submit', 'message'],
  <String>['odosli'],
  <String>['odoslat'],
  <String>['odosli', 'spravu'],
  <String>['posli'],
  <String>['poslat'],
  <String>['posli', 'spravu'],
  <String>['sende'],
  <String>['senden'],
  <String>['sende', 'nachricht'],
  <String>['nachricht', 'senden'],
  <String>['abschicken'],
  <String>['schick', 'ab'],
];

const Map<String, String> _fallbackGeneratedCaseTitleByLanguage =
    <String, String>{
  'SK': 'Nový prípad',
  'EN': 'New case',
  'GE': 'Neuer Fall',
};

const Set<String> _genericCaseTitleStopwords = <String>{
  'a',
  'about',
  'also',
  'and',
  'as',
  'bitte',
  'by',
  'for',
  'from',
  'help',
  'i',
  'ich',
  'im',
  'in',
  'ja',
  'me',
  'mi',
  'mit',
  'my',
  'na',
  'need',
  'new',
  'novy',
  'o',
  'of',
  'please',
  'potrebujem',
  'pre',
  'problem',
  'prosim',
  'question',
  's',
  'sa',
  'sie',
  'so',
  'start',
  'the',
  'to',
  'vam',
  'with',
  'you',
};

String generateCaseTitleFromDiscussion(
  String text, {
  String languageCode = _fallbackLanguageCode,
}) {
  final normalizedLanguage = normalizeSpeechLanguageCode(languageCode);
  final tokens = _tokenizeSpeechCommand(text);
  if (tokens.isEmpty) {
    return _fallbackGeneratedCaseTitleByLanguage[normalizedLanguage] ??
        _fallbackGeneratedCaseTitleByLanguage[_fallbackLanguageCode]!;
  }

  final meaningfulTokens = <String>[];
  for (final token in tokens) {
    final normalized = _normalizeSpeechCommandToken(token);
    if (normalized.isEmpty) {
      continue;
    }
    if (_genericCaseTitleStopwords.contains(normalized)) {
      continue;
    }
    if (normalized.length <= 2 && !RegExp(r'^\d+$').hasMatch(normalized)) {
      continue;
    }
    final sanitized = _sanitizeCaseTitleToken(token);
    if (sanitized.isEmpty) {
      continue;
    }
    meaningfulTokens.add(sanitized);
    if (meaningfulTokens.length >= 4) {
      break;
    }
  }

  final selectedTokens = meaningfulTokens.isNotEmpty
      ? meaningfulTokens
      : tokens
          .map(_sanitizeCaseTitleToken)
          .where((token) {
            if (token.isEmpty) {
              return false;
            }
            final normalized = _normalizeSpeechCommandToken(token);
            if (_genericCaseTitleStopwords.contains(normalized)) {
              return false;
            }
            return normalized.length > 2 ||
                RegExp(r'^\d+$').hasMatch(normalized);
          })
          .take(4)
          .toList(growable: false);

  if (selectedTokens.isEmpty) {
    return _fallbackGeneratedCaseTitleByLanguage[normalizedLanguage] ??
        _fallbackGeneratedCaseTitleByLanguage[_fallbackLanguageCode]!;
  }

  final title = selectedTokens.join(' ').trim();
  if (title.isEmpty) {
    return _fallbackGeneratedCaseTitleByLanguage[normalizedLanguage] ??
        _fallbackGeneratedCaseTitleByLanguage[_fallbackLanguageCode]!;
  }
  return title[0].toUpperCase() + title.substring(1);
}

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

SpokenConfirmationChoice? parseSpokenConfirmation(String spokenText) {
  final tokens = _tokenizeSpeechCommand(spokenText);
  if (tokens.isEmpty) {
    return null;
  }

  final normalized =
      tokens.map(_normalizeSpeechCommandToken).toList(growable: false);
  final filtered = normalized
      .skip(_skipLeadingPolitePrefixes(normalized))
      .toList(growable: false);
  if (filtered.isEmpty) {
    return null;
  }

  const yesPatterns = <List<String>>[
    <String>['yes'],
    <String>['yeah'],
    <String>['yep'],
    <String>['ok'],
    <String>['okay'],
    <String>['confirm'],
    <String>['continue'],
    <String>['proceed'],
    <String>['ano'],
    <String>['potvrd'],
    <String>['potvrdzujem'],
    <String>['pokracuj'],
    <String>['ja'],
  ];
  const noPatterns = <List<String>>[
    <String>['no'],
    <String>['nope'],
    <String>['cancel'],
    <String>['stop'],
    <String>['nie'],
    <String>['zrus'],
    <String>['nezakladaj'],
    <String>['ne'],
  ];

  if (yesPatterns.any((pattern) => _matchesExactPattern(filtered, pattern))) {
    return SpokenConfirmationChoice.yes;
  }
  if (noPatterns.any((pattern) => _matchesExactPattern(filtered, pattern))) {
    return SpokenConfirmationChoice.no;
  }
  return null;
}

SpokenCaseCreationCommand? parseSpokenCaseCreationCommand(String spokenText) {
  final tokens = _tokenizeSpeechCommand(spokenText);
  if (tokens.isEmpty) {
    return null;
  }

  final normalized =
      tokens.map(_normalizeSpeechCommandToken).toList(growable: false);
  final politePrefixLength = _skipLeadingPolitePrefixes(normalized);
  final filteredNormalized =
      normalized.skip(politePrefixLength).toList(growable: false);
  final prefixLength = _matchCaseCreationPrefixLength(filteredNormalized);
  if (prefixLength == null) {
    return null;
  }

  var titleStart = politePrefixLength + prefixLength;
  while (titleStart < tokens.length) {
    final nextIndex = _skipCaseTitleIntro(normalized, titleStart);
    if (nextIndex == titleStart) {
      break;
    }
    titleStart = nextIndex;
  }

  final titleTokens =
      tokens.sublist(titleStart).map(_sanitizeCaseTitleToken).where((token) {
    return token.isNotEmpty;
  }).toList(growable: false);
  final title = titleTokens.join(' ').trim();

  return SpokenCaseCreationCommand(
    title: title.isEmpty ? null : title,
  );
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

String? resolvePendingMessageForSendCommand({
  required String commandText,
  String? currentDraft,
  String? lastDictatedDraft,
}) {
  final trimmedCurrent = (currentDraft ?? '').trim();
  if (trimmedCurrent.isNotEmpty && !isSpokenSendCommand(trimmedCurrent)) {
    return trimmedCurrent;
  }
  final draft = (lastDictatedDraft ?? '').trim();
  if (draft.isEmpty || draft == commandText) {
    return null;
  }
  return draft;
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

bool _matchesExactPattern(List<String> tokens, List<String> pattern) {
  if (tokens.length != pattern.length) {
    return false;
  }
  for (var index = 0; index < pattern.length; index += 1) {
    if (tokens[index] != pattern[index]) {
      return false;
    }
  }
  return true;
}

int _skipLeadingPolitePrefixes(List<String> tokens) {
  var index = 0;
  while (index < tokens.length &&
      _sendCommandPolitePrefixes.contains(tokens[index])) {
    index += 1;
  }
  return index;
}

List<String> _tokenizeSpeechCommand(String spokenText) {
  return spokenText
      .replaceAll(RegExp(r'[.,!?;:"()]'), ' ')
      .split(RegExp(r'\s+'))
      .map((token) => token.trim())
      .where((token) => token.isNotEmpty)
      .toList(growable: false);
}

String _sanitizeCaseTitleToken(String token) {
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

String _normalizeSpeechCommandToken(String token) {
  final lowered = token.trim().toLowerCase();
  if (lowered.isEmpty) {
    return lowered;
  }
  const replacements = <String, String>{
    'á': 'a',
    'ä': 'a',
    'č': 'c',
    'ď': 'd',
    'é': 'e',
    'ě': 'e',
    'í': 'i',
    'ĺ': 'l',
    'ľ': 'l',
    'ň': 'n',
    'ó': 'o',
    'ô': 'o',
    'ö': 'o',
    'ř': 'r',
    'š': 's',
    'ť': 't',
    'ú': 'u',
    'ü': 'u',
    'ý': 'y',
    'ž': 'z',
    'ß': 'ss',
  };
  final buffer = StringBuffer();
  for (final rune in lowered.runes) {
    final character = String.fromCharCode(rune);
    buffer.write(replacements[character] ?? character);
  }
  return buffer.toString();
}

int? _matchCaseCreationPrefixLength(List<String> tokens) {
  const patterns = <List<String>>[
    <String>['create', 'a', 'new', 'case'],
    <String>['create', 'new', 'case'],
    <String>['create', 'a', 'case'],
    <String>['create', 'case'],
    <String>['open', 'a', 'new', 'case'],
    <String>['open', 'new', 'case'],
    <String>['new', 'case'],
    <String>['vytvor', 'mi', 'novy', 'pripad'],
    <String>['vytvor', 'mi', 'pripad'],
    <String>['vytvor', 'mi', 'novy', 'case'],
    <String>['vytvor', 'mi', 'case'],
    <String>['vytvor', 'novy', 'pripad'],
    <String>['vytvor', 'novy', 'case'],
    <String>['vytvor', 'case'],
    <String>['vytvor', 'pripad'],
    <String>['zaloz', 'novy', 'pripad'],
    <String>['zaloz', 'novy', 'case'],
    <String>['zaloz', 'pripad'],
    <String>['zaloz', 'case'],
    <String>['novy', 'pripad'],
    <String>['novy', 'case'],
    <String>['erstelle', 'einen', 'neuen', 'fall'],
    <String>['erstelle', 'einen', 'fall'],
    <String>['erstelle', 'fall'],
    <String>['neuen', 'fall'],
    <String>['neuer', 'fall'],
  ];

  for (final pattern in patterns) {
    if (tokens.length < pattern.length) {
      continue;
    }
    var matches = true;
    for (var index = 0; index < pattern.length; index += 1) {
      if (tokens[index] != pattern[index]) {
        matches = false;
        break;
      }
    }
    if (matches) {
      return pattern.length;
    }
  }
  return null;
}

int _skipCaseTitleIntro(List<String> tokens, int startIndex) {
  const intros = <List<String>>[
    <String>['with', 'name'],
    <String>['named'],
    <String>['called'],
    <String>['titled'],
    <String>['s', 'nazvom'],
    <String>['s', 'menom'],
    <String>['nazov'],
    <String>['mit', 'namen'],
    <String>['namens'],
  ];

  for (final intro in intros) {
    if (startIndex + intro.length > tokens.length) {
      continue;
    }
    var matches = true;
    for (var index = 0; index < intro.length; index += 1) {
      if (tokens[startIndex + index] != intro[index]) {
        matches = false;
        break;
      }
    }
    if (matches) {
      return startIndex + intro.length;
    }
  }
  return startIndex;
}


bool isSpokenDoneCommand(String spokenText) {
  final tokens = _tokenizeSpeechCommand(spokenText);
  if (tokens.isEmpty) return false;
  final normalized = tokens.map(_normalizeSpeechCommandToken).toList(growable: false);
  return _doneCommandPatterns.any((pattern) => _matchesExactPattern(normalized, pattern));
}

const List<List<String>> _doneCommandPatterns = <List<String>>[
  <String>['to', 'je', 'vsetko'],
  <String>['vsetko'],
  <String>['i', 'am', 'done'],
  <String>['alles'],
];
