import 'dart:convert';

import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

class SubscriptionPlanInfo {
  const SubscriptionPlanInfo({
    required this.planCode,
    required this.displayName,
    required this.subscriptionType,
    required this.priceEur,
    required this.maxCases,
    required this.maxDocumentsPerCase,
    this.caseTtlDays,
  });

  final String planCode;
  final String displayName;
  final String subscriptionType;
  final int priceEur;
  final int maxCases;
  final int maxDocumentsPerCase;
  final int? caseTtlDays;

  static SubscriptionPlanInfo fromJson(Map<String, dynamic> json) {
    return SubscriptionPlanInfo(
      planCode: json['plan_code'] as String? ?? '',
      displayName: json['display_name'] as String? ?? '',
      subscriptionType: json['subscription_type'] as String? ?? '',
      priceEur: json['price_eur'] as int? ?? 0,
      maxCases: json['max_cases'] as int? ?? 0,
      maxDocumentsPerCase: json['max_documents_per_case'] as int? ?? 0,
      caseTtlDays: json['case_ttl_days'] as int?,
    );
  }
}

class UserSubscriptionInfo {
  const UserSubscriptionInfo({
    required this.subscriptionId,
    required this.userId,
    required this.planCode,
    required this.status,
    this.startsAt,
    this.endsAt,
  });

  final String subscriptionId;
  final String userId;
  final String planCode;
  final String status;
  final String? startsAt;
  final String? endsAt;

  static UserSubscriptionInfo fromJson(Map<String, dynamic> json) {
    return UserSubscriptionInfo(
      subscriptionId: json['subscription_id'] as String? ?? '',
      userId: json['user_id'] as String? ?? '',
      planCode: json['plan_code'] as String? ?? '',
      status: json['status'] as String? ?? '',
      startsAt: json['starts_at'] as String?,
      endsAt: json['ends_at'] as String?,
    );
  }
}

class LocalAuthUser {
  const LocalAuthUser({
    required this.userId,
    required this.phoneNumber,
    required this.email,
    required this.password,
    this.firstName,
    this.lastName,
  });

  final String userId;
  final String phoneNumber;
  final String email;
  final String password;
  final String? firstName;
  final String? lastName;

  String get displayName {
    final first = (firstName ?? '').trim();
    final last = (lastName ?? '').trim();
    final joined = '$first $last'.trim();
    if (joined.isNotEmpty) {
      return joined;
    }
    return phoneNumber;
  }

  LocalAuthUser copyWith({
    String? userId,
    String? phoneNumber,
    String? email,
    String? password,
    String? firstName,
    String? lastName,
  }) {
    return LocalAuthUser(
      userId: userId ?? this.userId,
      phoneNumber: phoneNumber ?? this.phoneNumber,
      email: email ?? this.email,
      password: password ?? this.password,
      firstName: firstName ?? this.firstName,
      lastName: lastName ?? this.lastName,
    );
  }

  Map<String, dynamic> toJson() {
    return <String, dynamic>{
      'user_id': userId,
      'phone_number': phoneNumber,
      'email': email,
      'password': password,
      'first_name': firstName,
      'last_name': lastName,
    };
  }

  static LocalAuthUser fromJson(Map<String, dynamic> json) {
    return LocalAuthUser(
      userId: json['user_id'] as String? ?? '',
      phoneNumber: json['phone_number'] as String? ?? '',
      email: json['email'] as String? ?? '',
      password: json['password'] as String? ?? '',
      firstName: json['first_name'] as String?,
      lastName: json['last_name'] as String?,
    );
  }
}

class SignUpInput {
  const SignUpInput({
    required this.phoneNumber,
    required this.email,
    required this.password,
    required this.verificationCode,
    this.firstName,
    this.lastName,
  });

  final String phoneNumber;
  final String email;
  final String password;
  final String verificationCode;
  final String? firstName;
  final String? lastName;
}

class UpdateProfileInput {
  const UpdateProfileInput({
    required this.phoneNumber,
    required this.password,
    this.firstName,
    this.lastName,
  });

  final String phoneNumber;
  final String password;
  final String? firstName;
  final String? lastName;
}

class LocalAuthStore {
  static const String _currentUserKeyPrefix = 'mobile_auth_current_user_v3';
  static const String _lastPhoneKeyPrefix = 'mobile_auth_last_phone_v3';
  static const String _deviceTokenKeyPrefix = 'mobile_auth_device_token_v1';
  static const String _deviceIdKeyPrefix = 'mobile_auth_device_id_v1';

  const LocalAuthStore({
    required this.baseUri,
    required this.apiKey,
  });

  final Uri baseUri;
  final String apiKey;

  String get _currentUserKey => '${_currentUserKeyPrefix}_${_storageScope()}';
  String get _lastPhoneKey => '${_lastPhoneKeyPrefix}_${_storageScope()}';
  String get _deviceTokenKey => '${_deviceTokenKeyPrefix}_${_storageScope()}';
  String get _deviceIdKey => '${_deviceIdKeyPrefix}_${_storageScope()}';

  String _storageScope() {
    final buffer = StringBuffer()
      ..write(baseUri.scheme.toLowerCase())
      ..write('_')
      ..write(baseUri.host.toLowerCase());
    if (baseUri.hasPort) {
      buffer
        ..write('_')
        ..write(baseUri.port);
    }
    final normalizedPath = baseUri.path.trim();
    if (normalizedPath.isNotEmpty && normalizedPath != '/') {
      buffer
        ..write('_')
        ..write(normalizedPath);
    }
    return buffer
        .toString()
        .replaceAll(RegExp(r'[^a-z0-9]+'), '_')
        .replaceAll(RegExp(r'_+'), '_')
        .replaceFirst(RegExp(r'^_+'), '')
        .replaceFirst(RegExp(r'_+$'), '');
  }

  String _normalizePhone(String value) {
    final trimmed = value.trim();
    return trimmed.replaceAll(RegExp(r'\s+'), '');
  }

  String _normalizeEmail(String value) {
    return value.trim().toLowerCase();
  }

  String? _normalizeOptionalText(String? value) {
    if (value == null) {
      return null;
    }
    final trimmed = value.trim();
    if (trimmed.isEmpty) {
      return null;
    }
    return trimmed;
  }

  Map<String, String> get _headers => <String, String>{
        'x-api-key': apiKey,
        'Content-Type': 'application/json',
      };

  Future<LocalAuthUser?> getCurrentUser() async {
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getString(_currentUserKey);
    if (raw == null || raw.trim().isEmpty) {
      return null;
    }
    try {
      return LocalAuthUser.fromJson(
        jsonDecode(raw) as Map<String, dynamic>,
      );
    } catch (_) {
      await prefs.remove(_currentUserKey);
      return null;
    }
  }

  Future<String?> getLastPhoneNumber() async {
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getString(_lastPhoneKey);
    if (raw == null || raw.trim().isEmpty) {
      return null;
    }
    return raw;
  }

  Future<void> signOut() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_currentUserKey);
    await prefs.remove(_deviceTokenKey);
  }

  Future<String> getOrCreateDeviceBindingId() async {
    final prefs = await SharedPreferences.getInstance();
    final existing = prefs.getString(_deviceIdKey);
    if (existing != null && existing.trim().isNotEmpty) {
      return existing;
    }
    final created =
        'device_${DateTime.now().microsecondsSinceEpoch}_${baseUri.host}';
    await prefs.setString(_deviceIdKey, created);
    return created;
  }

  Future<LocalAuthUser> signUp(SignUpInput input) async {
    final phone = _normalizePhone(input.phoneNumber);
    final email = _normalizeEmail(input.email);
    final password = input.password.trim();
    final verificationCode = input.verificationCode.trim();
    if (phone.isEmpty) {
      throw Exception('Phone number is required.');
    }
    if (email.isEmpty) {
      throw Exception('Email is required.');
    }
    if (password.isEmpty) {
      throw Exception('Password is required.');
    }
    if (verificationCode.isEmpty) {
      throw Exception('Verification code is required.');
    }

    final response = await _postJson(
      path: '/v1/users/sign-up/complete',
      payload: <String, Object?>{
        'phone_number': phone,
        'email': email,
        'password': password,
        'verification_code': verificationCode,
        'first_name': _normalizeOptionalText(input.firstName),
        'last_name': _normalizeOptionalText(input.lastName),
      },
    );
    if (response.statusCode != 201) {
      throw Exception(_extractErrorDetail(response));
    }

    final user = _userFromApiResponse(response, password: password);
    await _cacheSignedInUser(user);
    return user;
  }

  Future<void> sendRegistrationCode({required String email}) async {
    final normalizedEmail = _normalizeEmail(email);
    if (normalizedEmail.isEmpty) {
      throw Exception('Email is required.');
    }
    final response = await _postJson(
      path: '/v1/users/sign-up/send-code',
      payload: <String, Object?>{'email': normalizedEmail},
    );
    if (response.statusCode != 202) {
      throw Exception(_extractErrorDetail(response));
    }
  }

  Future<void> sendSignInCode({
    required String phoneNumber,
    required String deviceId,
  }) async {
    final phone = _normalizePhone(phoneNumber);
    final resolvedDeviceId = deviceId.trim();
    if (phone.isEmpty) {
      throw Exception('Phone number is required.');
    }
    if (resolvedDeviceId.isEmpty) {
      throw Exception('Device id is required.');
    }
    final response = await _postJson(
      path: '/v1/users/sign-in/send-code',
      payload: <String, Object?>{
        'phone_number': phone,
        'device_id': resolvedDeviceId,
      },
    );
    if (response.statusCode != 202) {
      throw Exception(_extractErrorDetail(response));
    }
  }

  Future<LocalAuthUser?> signInByPhoneOtp({
    required String phoneNumber,
    required String verificationCode,
    required String deviceId,
  }) async {
    final phone = _normalizePhone(phoneNumber);
    final code = verificationCode.trim();
    final resolvedDeviceId = deviceId.trim();
    if (phone.isEmpty || code.isEmpty || resolvedDeviceId.isEmpty) {
      return null;
    }
    final response = await _postJson(
      path: '/v1/users/sign-in/verify-code',
      payload: <String, Object?>{
        'phone_number': phone,
        'verification_code': code,
        'device_id': resolvedDeviceId,
      },
    );
    if (response.statusCode != 200) {
      throw Exception(_extractErrorDetail(response));
    }
    final user = _userFromApiResponse(response, password: '');
    await _cacheSignedInUser(user);
    await _cacheDeviceToken(_deviceTokenFromApiResponse(response));
    return user;
  }

  Future<LocalAuthUser?> signInByDeviceToken({
    required String phoneNumber,
    required String deviceId,
  }) async {
    final phone = _normalizePhone(phoneNumber);
    final resolvedDeviceId = deviceId.trim();
    final prefs = await SharedPreferences.getInstance();
    final cachedToken = prefs.getString(_deviceTokenKey);
    if (phone.isEmpty ||
        resolvedDeviceId.isEmpty ||
        cachedToken == null ||
        cachedToken.trim().isEmpty) {
      return null;
    }
    final response = await _postJson(
      path: '/v1/users/sign-in/device',
      payload: <String, Object?>{
        'phone_number': phone,
        'device_id': resolvedDeviceId,
        'device_token': cachedToken.trim(),
      },
    );
    if (response.statusCode == 401) {
      await _cacheDeviceToken(null);
      return null;
    }
    if (response.statusCode != 200) {
      throw Exception(_extractErrorDetail(response));
    }
    final user = _userFromApiResponse(response, password: '');
    await _cacheSignedInUser(user);
    await _cacheDeviceToken(_deviceTokenFromApiResponse(response));
    return user;
  }

  Future<LocalAuthUser?> signInByPhone(String phoneNumber) async {
    final phone = _normalizePhone(phoneNumber);
    if (phone.isEmpty) {
      return null;
    }
    final response = await _postJson(
      path: '/v1/users/sign-in/phone',
      payload: <String, Object?>{'phone_number': phone},
    );
    if (response.statusCode == 404) {
      await _rememberLastPhone(phone);
      return null;
    }
    if (response.statusCode != 200) {
      throw Exception(_extractErrorDetail(response));
    }

    final current = await getCurrentUser();
    final cachedPassword =
        current != null && current.phoneNumber == phone ? current.password : '';
    final user = _userFromApiResponse(response, password: cachedPassword);
    await _cacheSignedInUser(user);
    return user;
  }

  Future<LocalAuthUser?> signInByEmailPassword({
    required String email,
    required String password,
  }) async {
    final normalizedEmail = _normalizeEmail(email);
    final normalizedPassword = password.trim();
    if (normalizedEmail.isEmpty || normalizedPassword.isEmpty) {
      return null;
    }
    final response = await _postJson(
      path: '/v1/users/sign-in',
      payload: <String, Object?>{
        'email': normalizedEmail,
        'password': normalizedPassword,
      },
    );
    if (response.statusCode == 401) {
      return null;
    }
    if (response.statusCode != 200) {
      throw Exception(_extractErrorDetail(response));
    }

    final user = _userFromApiResponse(response, password: normalizedPassword);
    await _cacheSignedInUser(user);
    return user;
  }

  Future<LocalAuthUser> updateUser({
    required UpdateProfileInput input,
  }) async {
    final current = await getCurrentUser();
    if (current == null || current.userId.isEmpty) {
      throw Exception('User account not found.');
    }

    final phone = _normalizePhone(input.phoneNumber);
    final password = input.password.trim();
    final resolvedPassword = password.isEmpty ? current.password : password;
    if (phone.isEmpty) {
      throw Exception('Phone number is required.');
    }

    final response = await _patchJson(
      path: '/v1/users/${current.userId}',
      payload: <String, Object?>{
        'phone_number': phone,
        'password': password.isEmpty ? null : password,
        'first_name': _normalizeOptionalText(input.firstName),
        'last_name': _normalizeOptionalText(input.lastName),
      },
    );
    if (response.statusCode != 200) {
      throw Exception(_extractErrorDetail(response));
    }

    final updated = _userFromApiResponse(response, password: resolvedPassword);
    await _cacheSignedInUser(updated);
    return updated;
  }

  Future<List<SubscriptionPlanInfo>> listSubscriptionPlans() async {
    final response = await http.get(
        baseUri.resolve('/v1/users/subscriptions/plans'),
        headers: _headers);
    if (response.statusCode != 200) {
      throw Exception(_extractErrorDetail(response));
    }
    final decoded = jsonDecode(response.body) as List<dynamic>;
    return decoded
        .whereType<Map<String, dynamic>>()
        .map(SubscriptionPlanInfo.fromJson)
        .toList(growable: false);
  }

  Future<List<UserSubscriptionInfo>> listUserSubscriptions(
      {required String userId}) async {
    final response = await http.get(
        baseUri.resolve('/v1/users/$userId/subscriptions'),
        headers: _headers);
    if (response.statusCode != 200) {
      throw Exception(_extractErrorDetail(response));
    }
    final decoded = jsonDecode(response.body) as List<dynamic>;
    return decoded
        .whereType<Map<String, dynamic>>()
        .map(UserSubscriptionInfo.fromJson)
        .toList(growable: false);
  }

  Future<UserSubscriptionInfo> requestSubscriptionChange(
      {required String userId, required String planCode}) async {
    final response = await _postJson(
      path: '/v1/users/$userId/subscriptions',
      payload: <String, Object?>{'plan_code': planCode},
    );
    if (response.statusCode != 201) {
      throw Exception(_extractErrorDetail(response));
    }
    return UserSubscriptionInfo.fromJson(
        jsonDecode(response.body) as Map<String, dynamic>);
  }

  Future<void> _cacheSignedInUser(LocalAuthUser user) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_currentUserKey, jsonEncode(user.toJson()));
    await _rememberLastPhone(user.phoneNumber);
  }

  Future<void> _rememberLastPhone(String? phoneNumber) async {
    final prefs = await SharedPreferences.getInstance();
    if (phoneNumber == null || phoneNumber.isEmpty) {
      await prefs.remove(_lastPhoneKey);
      return;
    }
    await prefs.setString(_lastPhoneKey, phoneNumber);
  }

  Future<void> _cacheDeviceToken(String? token) async {
    final prefs = await SharedPreferences.getInstance();
    if (token == null || token.trim().isEmpty) {
      await prefs.remove(_deviceTokenKey);
      return;
    }
    await prefs.setString(_deviceTokenKey, token.trim());
  }

  Future<http.Response> _postJson({
    required String path,
    required Map<String, Object?> payload,
  }) {
    return http.post(
      baseUri.resolve(path),
      headers: _headers,
      body: jsonEncode(payload),
    );
  }

  Future<http.Response> _patchJson({
    required String path,
    required Map<String, Object?> payload,
  }) {
    return http.patch(
      baseUri.resolve(path),
      headers: _headers,
      body: jsonEncode(payload),
    );
  }

  String _extractErrorDetail(http.Response response) {
    final body = response.body.trim();
    if (body.isEmpty) {
      return 'Request failed with status ${response.statusCode}.';
    }
    try {
      final decoded = jsonDecode(body);
      if (decoded is Map<String, dynamic>) {
        final detail = decoded['detail'] as Object?;
        if (detail is String && detail.trim().isNotEmpty) {
          return detail.trim();
        }
      }
    } catch (_) {
      // Fall through to raw body.
    }
    return body;
  }

  LocalAuthUser _userFromApiResponse(
    http.Response response, {
    required String password,
  }) {
    final decoded = jsonDecode(response.body) as Map<String, dynamic>;
    return LocalAuthUser(
      userId: decoded['user_id'] as String? ?? '',
      phoneNumber: decoded['phone_number'] as String? ?? '',
      email: decoded['email'] as String? ?? '',
      password: password,
      firstName: decoded['first_name'] as String?,
      lastName: decoded['last_name'] as String?,
    );
  }

  String? _deviceTokenFromApiResponse(http.Response response) {
    final decoded = jsonDecode(response.body) as Map<String, dynamic>;
    final token = decoded['device_auth_token'] as String?;
    if (token == null || token.trim().isEmpty) {
      return null;
    }
    return token.trim();
  }
}
