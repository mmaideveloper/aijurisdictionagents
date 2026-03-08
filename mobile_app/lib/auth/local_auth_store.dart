import 'dart:convert';

import 'package:shared_preferences/shared_preferences.dart';

class LocalAuthUser {
  const LocalAuthUser({
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
    String? phoneNumber,
    String? email,
    String? password,
    String? firstName,
    String? lastName,
  }) {
    return LocalAuthUser(
      phoneNumber: phoneNumber ?? this.phoneNumber,
      email: email ?? this.email,
      password: password ?? this.password,
      firstName: firstName ?? this.firstName,
      lastName: lastName ?? this.lastName,
    );
  }

  Map<String, dynamic> toJson() {
    return <String, dynamic>{
      'phone_number': phoneNumber,
      'email': email,
      'password': password,
      'first_name': firstName,
      'last_name': lastName,
    };
  }

  static LocalAuthUser fromJson(Map<String, dynamic> json) {
    return LocalAuthUser(
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
  static const String _usersKey = 'mobile_auth_users_v1';
  static const String _currentPhoneKey = 'mobile_auth_current_phone_v1';

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

  Future<List<LocalAuthUser>> _readUsers(SharedPreferences prefs) async {
    final raw = prefs.getString(_usersKey);
    if (raw == null || raw.trim().isEmpty) {
      return <LocalAuthUser>[];
    }
    try {
      final decoded = jsonDecode(raw) as List<dynamic>;
      return decoded
          .whereType<Map>()
          .map(
              (item) => LocalAuthUser.fromJson(Map<String, dynamic>.from(item)))
          .toList();
    } catch (_) {
      return <LocalAuthUser>[];
    }
  }

  Future<void> _writeUsers(
    SharedPreferences prefs,
    List<LocalAuthUser> users,
  ) async {
    final serialized = jsonEncode(users.map((user) => user.toJson()).toList());
    await prefs.setString(_usersKey, serialized);
  }

  Future<void> _setCurrentPhone(
    SharedPreferences prefs,
    String? phoneNumber,
  ) async {
    if (phoneNumber == null || phoneNumber.isEmpty) {
      await prefs.remove(_currentPhoneKey);
      return;
    }
    await prefs.setString(_currentPhoneKey, phoneNumber);
  }

  Future<LocalAuthUser?> getCurrentUser() async {
    final prefs = await SharedPreferences.getInstance();
    final currentPhone = prefs.getString(_currentPhoneKey);
    if (currentPhone == null || currentPhone.isEmpty) {
      return null;
    }
    final users = await _readUsers(prefs);
    for (final user in users) {
      if (_normalizePhone(user.phoneNumber) == _normalizePhone(currentPhone)) {
        return user;
      }
    }
    return null;
  }

  Future<void> signOut() async {
    final prefs = await SharedPreferences.getInstance();
    await _setCurrentPhone(prefs, null);
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
    final prefs = await SharedPreferences.getInstance();
    final users = await _readUsers(prefs);
    for (final user in users) {
      if (_normalizePhone(user.phoneNumber) == phone) {
        throw Exception('Phone number is already registered.');
      }
      if (_normalizeEmail(user.email) == email) {
        throw Exception('Email is already registered.');
      }
    }
    final created = LocalAuthUser(
      phoneNumber: phone,
      email: email,
      password: password,
      firstName: _normalizeOptionalText(input.firstName),
      lastName: _normalizeOptionalText(input.lastName),
    );
    users.add(created);
    await _writeUsers(prefs, users);
    await _setCurrentPhone(prefs, created.phoneNumber);
    return created;
  }

  Future<LocalAuthUser?> signInByPhone(String phoneNumber) async {
    final phone = _normalizePhone(phoneNumber);
    if (phone.isEmpty) {
      return null;
    }
    final prefs = await SharedPreferences.getInstance();
    final users = await _readUsers(prefs);
    for (final user in users) {
      if (_normalizePhone(user.phoneNumber) == phone) {
        await _setCurrentPhone(prefs, user.phoneNumber);
        return user;
      }
    }
    return null;
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
    final prefs = await SharedPreferences.getInstance();
    final users = await _readUsers(prefs);
    for (final user in users) {
      if (_normalizeEmail(user.email) == normalizedEmail &&
          user.password == normalizedPassword) {
        await _setCurrentPhone(prefs, user.phoneNumber);
        return user;
      }
    }
    return null;
  }

  Future<LocalAuthUser> updateUser({
    required String originalPhoneNumber,
    required UpdateProfileInput input,
  }) async {
    final originalPhone = _normalizePhone(originalPhoneNumber);
    final phone = _normalizePhone(input.phoneNumber);
    final password = input.password.trim();
    if (phone.isEmpty) {
      throw Exception('Phone number is required.');
    }
    if (password.isEmpty) {
      throw Exception('Password is required.');
    }
    final prefs = await SharedPreferences.getInstance();
    final users = await _readUsers(prefs);
    var index = -1;
    for (var i = 0; i < users.length; i += 1) {
      if (_normalizePhone(users[i].phoneNumber) == originalPhone) {
        index = i;
      } else if (_normalizePhone(users[i].phoneNumber) == phone) {
        throw Exception('Phone number is already used by another account.');
      }
    }
    if (index < 0) {
      throw Exception('User account not found.');
    }
    final existing = users[index];
    final updated = existing.copyWith(
      phoneNumber: phone,
      password: password,
      firstName: _normalizeOptionalText(input.firstName),
      lastName: _normalizeOptionalText(input.lastName),
    );
    users[index] = updated;
    await _writeUsers(prefs, users);
    await _setCurrentPhone(prefs, updated.phoneNumber);
    return updated;
  }
}
