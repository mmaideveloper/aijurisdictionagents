import 'intent_mapper.dart';

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

enum ProfilePatchField { firstName, lastName, address }

class SpokenProfilePatch {
  const SpokenProfilePatch({
    required this.field,
    required this.value,
  });

  final ProfilePatchField field;
  final String value;

  String get apiFieldName {
    return switch (field) {
      ProfilePatchField.firstName => 'first_name',
      ProfilePatchField.lastName => 'last_name',
      ProfilePatchField.address => 'address',
    };
  }
}

enum SpokenConfirmationChoice { yes, no }

class RuleEngineContext {
  const RuleEngineContext({
    required this.awaitingProfileName,
    required this.awaitingCaseArchiveConfirmation,
    required this.awaitingCaseTitle,
    required this.submitMessageWhenNoRuleMatches,
    this.awaitingProfileField = false,
    this.awaitingProfilePatchConfirmation = false,
    this.pendingProfilePatch,
    this.currentDraft,
    this.lastDictatedDraft,
    this.correlationId,
    this.caseId,
    this.userId,
    this.languageCode,
    this.redactSensitiveEntitiesBeforeSend = true,
  });

  final bool awaitingProfileName;
  final bool awaitingProfileField;
  final bool awaitingProfilePatchConfirmation;
  final SpokenProfilePatch? pendingProfilePatch;
  final bool awaitingCaseArchiveConfirmation;
  final bool awaitingCaseTitle;
  final bool submitMessageWhenNoRuleMatches;
  final String? currentDraft;
  final String? lastDictatedDraft;
  final String? correlationId;
  final String? caseId;
  final String? userId;
  final String? languageCode;
  final bool redactSensitiveEntitiesBeforeSend;
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

class RequestProfilePatchRuleAction extends RuleEngineAction {
  const RequestProfilePatchRuleAction({
    required this.patch,
    this.toolRequest,
  });

  final SpokenProfilePatch? patch;
  final ToolInvocationRequest? toolRequest;
}

class ConfirmProfilePatchRuleAction extends RuleEngineAction {
  const ConfirmProfilePatchRuleAction({
    required this.confirmation,
    required this.patch,
  });

  final SpokenConfirmationChoice? confirmation;
  final SpokenProfilePatch? patch;
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
    this.toolRequest,
  });

  final String? title;
  final ToolInvocationRequest? toolRequest;

  bool get requiresTitlePrompt => title == null || title!.trim().isEmpty;
}

class ToolInvocationRuleAction extends RuleEngineAction {
  const ToolInvocationRuleAction({
    required this.request,
  });

  final ToolInvocationRequest request;
}

class SendCurrentDraftRuleAction extends RuleEngineAction {
  const SendCurrentDraftRuleAction({
    required this.message,
  });

  final String message;
}

class ClearCurrentDraftRuleAction extends RuleEngineAction {
  const ClearCurrentDraftRuleAction();
}

class SubmitMessageRuleAction extends RuleEngineAction {
  const SubmitMessageRuleAction({
    required this.message,
  });

  final String message;
}

class RuleEngine {
  const RuleEngine({this.intentMapper = const IntentMapper()});

  final IntentMapper intentMapper;

  RuleEngineAction evaluate({
    required String input,
    required RuleEngineContext context,
  }) {
    final normalizedText = input.trim();
    if (normalizedText.isEmpty) {
      return const IgnoreRuleAction();
    }

    if (context.awaitingProfilePatchConfirmation) {
      return ConfirmProfilePatchRuleAction(
        confirmation: parseSpokenConfirmation(normalizedText),
        patch: context.pendingProfilePatch,
      );
    }

    if (context.awaitingCaseArchiveConfirmation) {
      return ConfirmCaseArchiveRuleAction(
        confirmation: parseSpokenConfirmation(normalizedText),
      );
    }

    if (context.awaitingCaseTitle) {
      final title = stripTrailingSpokenSendCommand(normalizedText);
      return CreateCaseRuleAction(title: title ?? normalizedText);
    }

    if (context.awaitingProfileName) {
      return StoreProfileNameRuleAction(
        profileName: parseSpokenProfileName(normalizedText),
      );
    }

    if (context.awaitingProfileField) {
      final patch = parseSpokenProfilePatchCommand(normalizedText);
      return RequestProfilePatchRuleAction(
        patch: patch,
        toolRequest: _mapProfilePatchIntentRequest(
          normalizedText,
          context,
          patch,
        ),
      );
    }

    final profilePatch = parseSpokenProfilePatchCommand(normalizedText);
    if (profilePatch != null) {
      return RequestProfilePatchRuleAction(
        patch: profilePatch,
        toolRequest: _mapProfilePatchIntentRequest(
          normalizedText,
          context,
          profilePatch,
        ),
      );
    }

    if (isSpokenClearDraftCommand(normalizedText)) {
      return const ClearCurrentDraftRuleAction();
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
      return CreateCaseRuleAction(
        title: caseCommand.title,
        toolRequest: _mapIntentRequest(
          normalizedText,
          context,
          intentName: 'create_case',
          slots: <String, Object?>{'title': caseCommand.title},
        ),
      );
    }

    final toolRequest = _mapKnownToolIntent(normalizedText, context);
    if (toolRequest != null) {
      return ToolInvocationRuleAction(request: toolRequest);
    }

    final message = stripTrailingSpokenSendCommand(normalizedText);
    if (message != null) {
      if (message.trim().isEmpty) {
        return const IgnoreRuleAction();
      }
      return SubmitMessageRuleAction(message: message);
    }

    if (!context.submitMessageWhenNoRuleMatches) {
      return const IgnoreRuleAction();
    }

    return SubmitMessageRuleAction(message: normalizedText);
  }

  ToolInvocationRequest? _mapKnownToolIntent(
    String normalizedText,
    RuleEngineContext context,
  ) {
    if (!_hasToolInvocationContext(context)) {
      return null;
    }
    final request = intentMapper.mapTranscript(
      transcript: normalizedText,
      correlationId: context.correlationId!,
      caseId: context.caseId,
      userId: context.userId!,
      languageCode: context.languageCode,
      redactSensitiveEntitiesBeforeSend:
          context.redactSensitiveEntitiesBeforeSend,
    );
    if (request.intent.isFallback) {
      return null;
    }
    return request;
  }

  ToolInvocationRequest? _mapIntentRequest(
    String normalizedText,
    RuleEngineContext context, {
    required String intentName,
    Map<String, Object?> slots = const <String, Object?>{},
  }) {
    if (!_hasToolInvocationContext(context)) {
      return null;
    }
    return intentMapper.buildRequest(
      intent: VoiceIntent(
        name: intentName,
        rawTranscript: normalizedText,
        languageCode: context.languageCode,
        slots: slots,
      ),
      correlationId: context.correlationId!,
      caseId: context.caseId,
      userId: context.userId!,
      redactSensitiveEntitiesBeforeSend:
          context.redactSensitiveEntitiesBeforeSend,
    );
  }

  ToolInvocationRequest? _mapProfilePatchIntentRequest(
    String normalizedText,
    RuleEngineContext context,
    SpokenProfilePatch? patch,
  ) {
    if (patch == null) {
      return null;
    }
    final intentName = switch (patch.field) {
      ProfilePatchField.firstName ||
      ProfilePatchField.lastName =>
        'update_profile_name',
      ProfilePatchField.address => 'update_profile_address',
    };
    return _mapIntentRequest(
      normalizedText,
      context,
      intentName: intentName,
      slots: <String, Object?>{
        patch.apiFieldName: patch.value,
      },
    );
  }
}

bool _hasToolInvocationContext(RuleEngineContext context) {
  return (context.correlationId ?? '').trim().isNotEmpty &&
      (context.userId ?? '').trim().isNotEmpty;
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

bool isSpokenClearDraftCommand(String spokenText) {
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
  return _clearDraftCommandPatterns
      .any((pattern) => _matchesExactPattern(filtered, pattern));
}

bool hasTrailingSpokenSendCommand(String spokenText) {
  final tokens = _tokenizeSpeechCommand(spokenText);
  if (tokens.isEmpty) {
    return false;
  }
  final normalized =
      tokens.map(_normalizeSpeechCommandToken).toList(growable: false);
  final suffixLength = _trailingSendCommandLength(normalized);
  return suffixLength != null && tokens.length > suffixLength;
}

String? stripTrailingSpokenSendCommand(String spokenText) {
  final tokens = _tokenizeSpeechCommand(spokenText);
  if (tokens.isEmpty) {
    return null;
  }
  final normalized =
      tokens.map(_normalizeSpeechCommandToken).toList(growable: false);
  final suffixLength = _trailingSendCommandLength(normalized);
  if (suffixLength == null || tokens.length <= suffixLength) {
    return null;
  }
  final titleTokens = tokens
      .take(tokens.length - suffixLength)
      .map(_sanitizeCaseTitleToken)
      .where((token) => token.isNotEmpty)
      .toList(growable: false);
  return titleTokens.join(' ').trim();
}

const String _fallbackLanguageCode = 'SK';

const Set<String> _sendCommandPolitePrefixes = <String>{
  'dobre',
  'hej',
  'ok',
  'okay',
  'poprosim',
  'please',
  'prosim',
  'ta',
  'vas',
  'bitte',
  'este',
  'raz',
};

const List<List<String>> _sendCommandPatterns = <List<String>>[
  <String>['send'],
  <String>['send', 'it'],
  <String>['send', 'message'],
  <String>['send', 'the', 'message'],
  <String>['end'],
  <String>['submit'],
  <String>['submit', 'message'],
  <String>['i', 'am', 'done'],
  <String>['im', 'done'],
  <String>['this', 'is', 'end'],
  <String>['this', 'is', 'the', 'end'],
  <String>['odosli'],
  <String>['odoslat'],
  <String>['odosli', 'spravu'],
  <String>['koniec'],
  <String>['posli'],
  <String>['poslat'],
  <String>['posli', 'spravu'],
  <String>['to', 'je', 'vsetko'],
  <String>['cakam', 'na', 'odpoved'],
  <String>['sende'],
  <String>['senden'],
  <String>['sende', 'nachricht'],
  <String>['nachricht', 'senden'],
  <String>['abschicken'],
  <String>['schick', 'ab'],
];

const List<List<String>> _clearDraftCommandPatterns = <List<String>>[
  <String>['zrus', 'vsetko'],
  <String>['zrus', 'spravu'],
  <String>['vymaz', 'vsetko'],
  <String>['cancel', 'everything'],
  <String>['clean', 'message'],
  <String>['clean', 'last', 'message'],
  <String>['clear', 'message'],
  <String>['clear', 'draft'],
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
    <String>['abbrechen'],
    <String>['nie'],
    <String>['zrus'],
    <String>['nezakladaj'],
    <String>['ne'],
    <String>['nein'],
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
  final title = stripTrailingSpokenSendCommand(titleTokens.join(' ')) ??
      titleTokens.join(' ').trim();

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

SpokenProfilePatch? parseSpokenProfilePatchCommand(String spokenText) {
  final normalizedText = spokenText.trim();
  if (normalizedText.isEmpty) {
    return null;
  }

  final patterns = <({ProfilePatchField field, RegExp pattern})>[
    (
      field: ProfilePatchField.firstName,
      pattern: RegExp(
        r'^(?:pros[ií]m\s+)?(?:zme[nň]|zmenit|nastav|nastavte)\s+(?:mi\s+)?meno\s+na\s+(.+)$',
        caseSensitive: false,
      ),
    ),
    (
      field: ProfilePatchField.firstName,
      pattern: RegExp(
        r'^(?:please\s+)?(?:change|set|update)\s+(?:my\s+)?(?:first\s+name|name)\s+to\s+(.+)$',
        caseSensitive: false,
      ),
    ),
    (
      field: ProfilePatchField.firstName,
      pattern: RegExp(
        r'^(?:bitte\s+)?(?:[äa]ndere|setze|aktualisiere)\s+(?:meinen\s+)?(?:vornamen|namen)\s+(?:auf|zu)\s+(.+)$',
        caseSensitive: false,
      ),
    ),
    (
      field: ProfilePatchField.lastName,
      pattern: RegExp(
        r'^(?:pros[ií]m\s+)?(?:zme[nň]|zmenit|nastav|nastavte)\s+(?:mi\s+)?priezvisko\s+na\s+(.+)$',
        caseSensitive: false,
      ),
    ),
    (
      field: ProfilePatchField.lastName,
      pattern: RegExp(
        r'^(?:please\s+)?(?:change|set|update)\s+(?:my\s+)?last\s+name\s+to\s+(.+)$',
        caseSensitive: false,
      ),
    ),
    (
      field: ProfilePatchField.lastName,
      pattern: RegExp(
        r'^(?:bitte\s+)?(?:[äa]ndere|setze|aktualisiere)\s+(?:meinen\s+)?nachnamen\s+(?:auf|zu)\s+(.+)$',
        caseSensitive: false,
      ),
    ),
    (
      field: ProfilePatchField.address,
      pattern: RegExp(
        r'^(?:pros[ií]m\s+)?(?:zme[nň]|zmenit|nastav|nastavte)\s+(?:mi\s+)?adresu\s+na\s+(.+)$',
        caseSensitive: false,
      ),
    ),
    (
      field: ProfilePatchField.address,
      pattern: RegExp(
        r'^(?:please\s+)?(?:change|set|update)\s+(?:my\s+)?address\s+to\s+(.+)$',
        caseSensitive: false,
      ),
    ),
    (
      field: ProfilePatchField.address,
      pattern: RegExp(
        r'^(?:bitte\s+)?(?:[äa]ndere|setze|aktualisiere)\s+(?:meine\s+)?adresse\s+(?:auf|zu)\s+(.+)$',
        caseSensitive: false,
      ),
    ),
  ];

  for (final entry in patterns) {
    final match = entry.pattern.firstMatch(normalizedText);
    if (match == null) {
      continue;
    }
    final rawValue = match.group(1) ?? '';
    final value = switch (entry.field) {
      ProfilePatchField.firstName ||
      ProfilePatchField.lastName =>
        _normalizeProfileNamePatchValue(rawValue),
      ProfilePatchField.address => normalizeProfileAddress(rawValue),
    };
    if (value == null || value.isEmpty) {
      return null;
    }
    return SpokenProfilePatch(field: entry.field, value: value);
  }

  return null;
}

String? normalizeProfileAddress(String rawValue) {
  var value = rawValue.trim();
  if (value.isEmpty) {
    return null;
  }
  value = value.replaceAll(RegExp(r'\s+'), ' ');
  value = value.replaceAll(RegExp(r'\s*,\s*'), ', ');
  value = value.replaceAll(RegExp(r'\s*/\s*'), '/');
  value = _trimProfilePatchEdges(value);
  if (value.length < 6) {
    return null;
  }
  if (RegExp(r'[\x00-\x1F<>[\]{}|\\]').hasMatch(value)) {
    return null;
  }
  return value;
}

String? _normalizeProfileNamePatchValue(String rawValue) {
  final value = _trimProfilePatchEdges(rawValue.replaceAll(
    RegExp(r'\s+'),
    ' ',
  ));
  if (value.isEmpty) {
    return null;
  }
  final tokens = value
      .split(RegExp(r'\s+'))
      .map(_sanitizeNameToken)
      .where((token) => token.isNotEmpty)
      .toList(growable: false);
  if (tokens.isEmpty ||
      tokens.length > 3 ||
      tokens.any(_isClearlyInvalidNameToken)) {
    return null;
  }
  return tokens.join(' ');
}

String _trimProfilePatchEdges(String rawValue) {
  var value = rawValue.trim();
  const edgeCharacters = ' \t\r\n_,.?!;:"\'`()[]{}';
  while (value.isNotEmpty && edgeCharacters.contains(value[0])) {
    value = value.substring(1);
  }
  while (value.isNotEmpty && edgeCharacters.contains(value[value.length - 1])) {
    value = value.substring(0, value.length - 1);
  }
  return value.trim();
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
      .replaceAll(RegExp(r'[,!?;:"()]'), ' ')
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
  final lowered = _trimSpeechCommandTokenEdges(token).toLowerCase();
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

String _trimSpeechCommandTokenEdges(String token) {
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
    <String>['vytvor', 'mi', 'prosim', 'novy', 'pripad'],
    <String>['vytvor', 'prosim', 'novy', 'pripad'],
    <String>['vytvor', 'prosim', 'pripad'],
    <String>['vytvor', 'mi', 'novy', 'case'],
    <String>['vytvor', 'mi', 'case'],
    <String>['vytvor', 'novy', 'pripad'],
    <String>['vytvor', 'novy', 'case'],
    <String>['vytvor', 'case'],
    <String>['vytvor', 'pripad'],
    <String>['vytvorit', 'novy', 'pripad'],
    <String>['vytvorit', 'novy', 'case'],
    <String>['vytvorit', 'pripad'],
    <String>['vytvorit', 'case'],
    <String>['vytvor', 'novy', 'pripad', 'prosim'],
    <String>['chcem', 'zalozit', 'novy', 'pripad'],
    <String>['chcem', 'zalozit', 'pripad'],
    <String>['chcel', 'by', 'som', 'vytvorit', 'novy', 'pripad'],
    <String>['chcel', 'by', 'som', 'vytvorit', 'pripad'],
    <String>['chcela', 'by', 'som', 'vytvorit', 'novy', 'pripad'],
    <String>['chcela', 'by', 'som', 'vytvorit', 'pripad'],
    <String>['chcem', 'vytvorit', 'novy', 'pripad'],
    <String>['chcem', 'vytvorit', 'novy', 'case'],
    <String>['chcem', 'vytvorit', 'pripad'],
    <String>['chcem', 'vytvorit', 'case'],
    <String>['potrebujem', 'vytvorit', 'novy', 'pripad'],
    <String>['potrebujem', 'vytvorit', 'novy', 'case'],
    <String>['potrebujem', 'vytvorit', 'pripad'],
    <String>['potrebujem', 'vytvorit', 'case'],
    <String>['zaloz', 'novy', 'pripad'],
    <String>['zaloz', 'novy', 'case'],
    <String>['zaloz', 'pripad'],
    <String>['zaloz', 'case'],
    <String>['potrebujem', 'zalozit', 'novy', 'pripad'],
    <String>['potrebujem', 'zalozit', 'novy', 'case'],
    <String>['potrebujem', 'zalozit', 'pripad'],
    <String>['potrebujem', 'zalozit', 'case'],
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
    <String>['s', 'nazovom'],
    <String>['s', 'menom'],
    <String>['pod', 'nazvom'],
    <String>['pod', 'nazovom'],
    <String>['meno', 'pripadu'],
    <String>['nazov', 'pripadu'],
    <String>['nazov'],
    <String>['nazovom'],
    <String>['bude', 'sa', 'volat'],
    <String>['vola', 'sa'],
    <String>['je'],
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

int? _trailingSendCommandLength(List<String> normalizedTokens) {
  if (normalizedTokens.isEmpty) {
    return null;
  }

  final patterns = _sendCommandPatterns.toList(growable: false)
    ..sort((left, right) => right.length.compareTo(left.length));
  for (final pattern in patterns) {
    if (normalizedTokens.length < pattern.length) {
      continue;
    }
    var matches = true;
    final start = normalizedTokens.length - pattern.length;
    for (var index = 0; index < pattern.length; index += 1) {
      if (normalizedTokens[start + index] != pattern[index]) {
        matches = false;
        break;
      }
    }
    if (!matches) {
      continue;
    }

    var suffixLength = pattern.length;
    final politePrefixIndex = start - 1;
    if (politePrefixIndex >= 0 &&
        _sendCommandPolitePrefixes
            .contains(normalizedTokens[politePrefixIndex])) {
      suffixLength += 1;
    }
    return suffixLength;
  }
  return null;
}
