import '../voice_compliance.dart';

const String genericToolRequestIntentName = 'generic_tool_request';

class VoiceIntent {
  const VoiceIntent({
    required this.name,
    required this.rawTranscript,
    this.languageCode,
    this.slots = const <String, Object?>{},
    this.metadata = const <String, Object?>{},
  });

  final String name;
  final String rawTranscript;
  final String? languageCode;
  final Map<String, Object?> slots;
  final Map<String, Object?> metadata;

  bool get isFallback => name == genericToolRequestIntentName;
}

class ToolInvocationRequest {
  const ToolInvocationRequest({
    required this.toolName,
    required this.intent,
    required this.payload,
  });

  final String toolName;
  final VoiceIntent intent;
  final Map<String, Object?> payload;

  Map<String, Object?> toJson() {
    return <String, Object?>{
      'tool_name': toolName,
      'intent': intent.name,
      'payload': payload,
    };
  }
}

class ToolInvocationResult {
  const ToolInvocationResult({
    required this.toolName,
    required this.succeeded,
    this.payload = const <String, Object?>{},
    this.errorMessage,
    this.correlationId,
  });

  final String toolName;
  final bool succeeded;
  final Map<String, Object?> payload;
  final String? errorMessage;
  final String? correlationId;

  Map<String, Object?> toJson() {
    return <String, Object?>{
      'tool_name': toolName,
      'succeeded': succeeded,
      'payload': payload,
      if (errorMessage != null) 'error_message': errorMessage,
      if (correlationId != null) 'correlation_id': correlationId,
    };
  }
}

class IntentMapper {
  const IntentMapper();

  ToolInvocationRequest mapTranscript({
    required String transcript,
    required String correlationId,
    required String? caseId,
    required String userId,
    String? languageCode,
    Map<String, Object?> metadata = const <String, Object?>{},
    bool redactSensitiveEntitiesBeforeSend =
        defaultRedactSensitiveEntitiesBeforeSend,
  }) {
    final intent = parseTranscript(
      transcript: transcript,
      languageCode: languageCode,
      metadata: metadata,
      redactSensitiveEntitiesBeforeSend: redactSensitiveEntitiesBeforeSend,
    );
    return buildRequest(
      intent: intent,
      correlationId: correlationId,
      caseId: caseId,
      userId: userId,
      redactSensitiveEntitiesBeforeSend: redactSensitiveEntitiesBeforeSend,
    );
  }

  VoiceIntent parseTranscript({
    required String transcript,
    String? languageCode,
    Map<String, Object?> metadata = const <String, Object?>{},
    bool redactSensitiveEntitiesBeforeSend =
        defaultRedactSensitiveEntitiesBeforeSend,
  }) {
    final normalizedTranscript = transcript.trim();
    final safeTranscript = redactSensitiveEntitiesBeforeSend
        ? redactSensitiveEntities(normalizedTranscript)
        : normalizedTranscript;
    final normalized = _normalizeText(normalizedTranscript);
    final intentName = _matchIntentName(normalized);
    if (intentName == null) {
      return VoiceIntent(
        name: genericToolRequestIntentName,
        rawTranscript: safeTranscript,
        languageCode: languageCode,
        metadata: metadata,
      );
    }

    return VoiceIntent(
      name: intentName,
      rawTranscript: safeTranscript,
      languageCode: languageCode,
      slots: _extractSlots(
        intentName: intentName,
        transcript: normalizedTranscript,
        normalizedTranscript: normalized,
      ),
      metadata: metadata,
    );
  }

  ToolInvocationRequest buildRequest({
    required VoiceIntent intent,
    required String correlationId,
    required String? caseId,
    required String userId,
    bool redactSensitiveEntitiesBeforeSend =
        defaultRedactSensitiveEntitiesBeforeSend,
  }) {
    final toolName =
        intent.isFallback ? genericToolRequestIntentName : intent.name;
    final payload = <String, Object?>{
      'tool_name': toolName,
      'intent': intent.name,
      'correlation_id': correlationId,
      'case_id': _emptyToNull(caseId),
      'user_id': userId,
      'inputs': intent.slots,
      'metadata': <String, Object?>{
        'source': 'voice',
        'transcript_preview': intent.rawTranscript,
        'transcript_redacted': redactSensitiveEntitiesBeforeSend,
        'transcript_length': intent.rawTranscript.length,
        if (intent.languageCode != null) 'language': intent.languageCode,
        ...intent.metadata,
      },
    };
    return ToolInvocationRequest(
      toolName: toolName,
      intent: intent,
      payload: payload,
    );
  }
}

String? _matchIntentName(String normalizedTranscript) {
  for (final entry in _intentPatterns.entries) {
    if (entry.value.any(normalizedTranscript.contains)) {
      return entry.key;
    }
  }
  return null;
}

Map<String, Object?> _extractSlots({
  required String intentName,
  required String transcript,
  required String normalizedTranscript,
}) {
  switch (intentName) {
    case 'create_case':
      return <String, Object?>{
        'title': _trimmedOrNull(_removeCaseTitleIntro(_removeIntentPrefix(
          transcript,
          normalizedTranscript,
          _intentPatterns['create_case']!,
        ))),
      };
    case 'update_profile_name':
      return <String, Object?>{
        'display_name': _trimmedOrNull(_removeIntentPrefix(
          transcript,
          normalizedTranscript,
          _intentPatterns['update_profile_name']!,
        )),
      };
    case 'update_profile_address':
    case 'verify_address':
      return <String, Object?>{
        'address': _trimmedOrNull(_removeIntentPrefix(
          transcript,
          normalizedTranscript,
          _intentPatterns[intentName]!,
        )),
      };
    case 'send_document_email':
      return <String, Object?>{
        'email':
            RegExp(r'[\w.\-+]+@[\w.\-]+\.\w+').firstMatch(transcript)?.group(0),
      };
    case 'verify_company':
      return <String, Object?>{
        'company_query': _trimmedOrNull(_removeIntentPrefix(
          transcript,
          normalizedTranscript,
          _intentPatterns['verify_company']!,
        )),
      };
    case 'verify_person':
      return <String, Object?>{
        'person_query': _trimmedOrNull(_removeIntentPrefix(
          transcript,
          normalizedTranscript,
          _intentPatterns['verify_person']!,
        )),
      };
    case 'verify_property_cadastre':
      return <String, Object?>{
        'property_query': _trimmedOrNull(_removeIntentPrefix(
          transcript,
          normalizedTranscript,
          _intentPatterns['verify_property_cadastre']!,
        )),
      };
    case 'verify_vehicle':
      return <String, Object?>{
        'vehicle_query': _trimmedOrNull(_removeIntentPrefix(
          transcript,
          normalizedTranscript,
          _intentPatterns['verify_vehicle']!,
        )),
      };
    case 'generate_documentation':
    default:
      return const <String, Object?>{};
  }
}

String? _removeIntentPrefix(
  String transcript,
  String normalizedTranscript,
  List<String> patterns,
) {
  for (final pattern in patterns) {
    final index = normalizedTranscript.indexOf(pattern);
    if (index < 0) {
      continue;
    }
    final prefixLength = pattern.length;
    if (normalizedTranscript.length <= index + prefixLength) {
      return null;
    }
    final rawTail = transcript.substring(
      index + prefixLength > transcript.length
          ? transcript.length
          : index + prefixLength,
    );
    return rawTail.replaceFirst(RegExp(r'^\s*(for|pre|fur|für|of|:)\s*'), '');
  }
  return null;
}

String? _removeCaseTitleIntro(String? value) {
  final trimmed = (value ?? '').trim();
  if (trimmed.isEmpty) {
    return null;
  }
  return trimmed
      .replaceFirst(
        RegExp(
          r'^(s\s+nazvom|s\s+menom|nazov|with\s+name|named|called|titled|mit\s+namen|namens)\s+',
          caseSensitive: false,
        ),
        '',
      )
      .trim();
}

String? _trimmedOrNull(String? value) {
  final trimmed = (value ?? '').trim();
  if (trimmed.isEmpty) {
    return null;
  }
  return trimmed;
}

String? _emptyToNull(String? value) {
  final trimmed = (value ?? '').trim();
  if (trimmed.isEmpty) {
    return null;
  }
  return trimmed;
}

String _normalizeText(String value) {
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
  for (final rune in value.trim().toLowerCase().runes) {
    final character = String.fromCharCode(rune);
    buffer.write(replacements[character] ?? character);
  }
  return buffer
      .toString()
      .replaceAll(RegExp(r'[.,!?;:"()]'), ' ')
      .replaceAll(RegExp(r'\s+'), ' ')
      .trim();
}

const Map<String, List<String>> _intentPatterns = <String, List<String>>{
  'create_case': <String>[
    'create a new case',
    'create new case',
    'create case',
    'open a new case',
    'open new case',
    'new case',
    'vytvor mi novy pripad',
    'vytvor novy pripad',
    'vytvor pripad',
    'zaloz novy pripad',
    'zaloz pripad',
    'novy pripad',
    'erstelle einen neuen fall',
    'erstelle fall',
    'neuer fall',
  ],
  'update_profile_name': <String>[
    'update profile name',
    'change my name',
    'my name is',
    'zmen meno',
    'aktualizuj meno',
    'volam sa',
    'profilove meno',
    'profil meno',
    'profilname andern',
    'mein name ist',
  ],
  'update_profile_address': <String>[
    'update profile address',
    'change my address',
    'my address is',
    'zmen adresu',
    'aktualizuj adresu',
    'moja adresa je',
    'adresse andern',
    'meine adresse ist',
  ],
  'generate_documentation': <String>[
    'generate documentation',
    'generate document',
    'prepare documentation',
    'create documentation',
    'vygeneruj dokumentaciu',
    'vytvor dokumentaciu',
    'priprav dokument',
    'dokumentation erstellen',
    'dokument generieren',
  ],
  'send_document_email': <String>[
    'send document email',
    'send document by email',
    'email the document',
    'posli dokument emailom',
    'odosli dokument emailom',
    'dokument per email senden',
  ],
  'verify_company': <String>[
    'verify company',
    'check company',
    'over firmu',
    'over spolocnost',
    'skontroluj firmu',
    'firma prufen',
    'unternehmen prufen',
  ],
  'verify_address': <String>[
    'verify address',
    'check address',
    'over adresu',
    'skontroluj adresu',
    'adresse prufen',
  ],
  'verify_person': <String>[
    'verify person',
    'check person',
    'over osobu',
    'skontroluj osobu',
    'person prufen',
  ],
  'verify_property_cadastre': <String>[
    'verify property cadastre',
    'check cadastre',
    'check property',
    'over kataster',
    'over nehnutelnost',
    'skontroluj kataster',
    'grundbuch prufen',
    'liegenschaft prufen',
  ],
  'verify_vehicle': <String>[
    'verify vehicle',
    'check vehicle',
    'over vozidlo',
    'skontroluj vozidlo',
    'fahrzeug prufen',
  ],
};
