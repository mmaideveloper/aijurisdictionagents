const Set<String> _sensitiveKeys = <String>{
  'address',
  'body',
  'city',
  'content',
  'date_of_birth',
  'device_auth_token',
  'device_id',
  'device_token',
  'email',
  'error_message',
  'first_name',
  'html',
  'identity_card_number',
  'last_name',
  'message',
  'password',
  'payload',
  'phone_number',
  'raw_transcript',
  'social_security_number',
  'stack_trace',
  'tax_number',
  'token',
  'transcript',
  'verification_code',
  'zip_code',
};

Object? sanitizeLogValue(Object? value, {String? key}) {
  final normalizedKey = (key ?? '').trim().toLowerCase();
  if (_sensitiveKeys.contains(normalizedKey)) {
    return _metadataForSensitiveValue(value);
  }
  if (value is Map) {
    return <String, Object?>{
      for (final entry in value.entries)
        entry.key.toString(): sanitizeLogValue(
          entry.value,
          key: entry.key.toString(),
        ),
    };
  }
  if (value is Iterable) {
    return <Object?>[
      for (final item in value) sanitizeLogValue(item),
    ];
  }
  if (value is String && value.length > 240) {
    return <String, Object?>{
      'redacted': true,
      'length': value.length,
    };
  }
  return value;
}

Map<String, Object?> sanitizeLogContext(Map<String, Object?> context) {
  return <String, Object?>{
    for (final entry in context.entries)
      entry.key: sanitizeLogValue(entry.value, key: entry.key),
  };
}

Object _metadataForSensitiveValue(Object? value) {
  if (value == null) {
    return <String, Object?>{'redacted': true, 'present': false};
  }
  if (value is String) {
    return <String, Object?>{
      'redacted': true,
      'present': value.trim().isNotEmpty,
      'length': value.length,
    };
  }
  if (value is Map) {
    return <String, Object?>{
      'redacted': true,
      'field_count': value.length,
    };
  }
  if (value is Iterable) {
    return <String, Object?>{
      'redacted': true,
      'item_count': value.length,
    };
  }
  return <String, Object?>{'redacted': true, 'present': true};
}
