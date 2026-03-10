import 'dart:convert';

import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

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
    this.firstName,
    this.lastName,
  });

  final String phoneNumber;
  final String email;
  final String password;
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
  static const String _currentUserKey = 'mobile_auth_current_user_v2';
  static const String _lastPhoneKey = 'mobile_auth_last_phone_v2';

  const LocalAuthStore({
    required this.baseUri,
    required this.apiKey,
  });

  final Uri baseUri;
  final String apiKey;

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
  }

  Future<LocalAuthUser> signUp(SignUpInput input) async {
    final phone = _normalizePhone(input.phoneNumber);
    final email = _normalizeEmail(input.email);
    final password = input.password.trim();
    if (phone.isEmpty) {
      throw Exception('Phone number is required.');
    }
    if (email.isEmpty) {
      throw Exception('Email is required.');
    }
    if (password.isEmpty) {
      throw Exception('Password is required.');
    }

    final response = await _postJson(
      path: '/v1/users/sign-up',
      payload: <String, Object?>{
        'phone_number': phone,
        'email': email,
        'password': password,
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
    final cachedPassword = current != null && current.phoneNumber == phone
        ? current.password
        : '';
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
    if (phone.isEmpty) {
      throw Exception('Phone number is required.');
    }
    if (password.isEmpty) {
      throw Exception('Password is required.');
    }

    final response = await _patchJson(
      path: '/v1/users/${current.userId}',
      payload: <String, Object?>{
        'phone_number': phone,
        'password': password,
        'first_name': _normalizeOptionalText(input.firstName),
        'last_name': _normalizeOptionalText(input.lastName),
      },
    );
    if (response.statusCode != 200) {
      throw Exception(_extractErrorDetail(response));
    }

    final updated = _userFromApiResponse(response, password: password);
    await _cacheSignedInUser(updated);
    return updated;
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
}
