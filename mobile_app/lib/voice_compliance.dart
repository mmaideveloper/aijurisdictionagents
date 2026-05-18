class VoiceComplianceFlags {
  const VoiceComplianceFlags({
    required this.consentGiven,
    required this.storeAudioEnabled,
    required this.redactSensitiveEntitiesBeforeSend,
  });

  final bool consentGiven;
  final bool storeAudioEnabled;
  final bool redactSensitiveEntitiesBeforeSend;

  Map<String, Object?> toLogContext() {
    return <String, Object?>{
      'consent_given': consentGiven,
      'store_audio_enabled': storeAudioEnabled,
      'redact_sensitive_entities_before_send':
          redactSensitiveEntitiesBeforeSend,
    };
  }
}

const bool defaultVoiceConsentGiven = false;
const bool defaultStoreAudioEnabled = false;
const bool defaultRedactSensitiveEntitiesBeforeSend = true;

const VoiceComplianceFlags defaultVoiceComplianceFlags = VoiceComplianceFlags(
  consentGiven: defaultVoiceConsentGiven,
  storeAudioEnabled: defaultStoreAudioEnabled,
  redactSensitiveEntitiesBeforeSend: defaultRedactSensitiveEntitiesBeforeSend,
);

String redactSensitiveEntities(String value) {
  var redacted = value;
  redacted = redacted.replaceAll(
    RegExp(r'[\w.\-+]+@[\w.\-]+\.\w+'),
    '[redacted-email]',
  );
  redacted = redacted.replaceAll(
    RegExp(r'(?<!\d)(?:\+?\d[\d\s()./-]{6,}\d)(?!\d)'),
    '[redacted-number]',
  );
  redacted = redacted.replaceAll(
    RegExp(
      r'\b(?:rodn[eé]\s+[cč][ií]slo|social\s+security\s+number|ssn|tax\s+number|dic|di[cč]|identity\s+card|ob[cč]iansk[ye]\s+preukaz)\b\s*[:#-]?\s*[\w./-]+',
      caseSensitive: false,
    ),
    '[redacted-identifier]',
  );
  return redacted;
}
