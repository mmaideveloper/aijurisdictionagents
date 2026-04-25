import 'dart:convert';

import 'package:ai_jurisdiction_mobile/auth/local_auth_store.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('current user cache is scoped by API base URL', () async {
    SharedPreferences.setMockInitialValues({
      'mobile_auth_current_user_v3_http_127_0_0_1_8080': jsonEncode({
        'user_id': 'local-user',
        'phone_number': '+421900000001',
        'email': 'local@example.com',
        'password': 'local-pass',
        'first_name': 'Local',
        'last_name': 'User',
      }),
      'mobile_auth_current_user_v3_https_api_juris_dev_example_com': jsonEncode({
        'user_id': 'dev-user',
        'phone_number': '+421900000002',
        'email': 'dev@example.com',
        'password': 'dev-pass',
        'first_name': 'Dev',
        'last_name': 'User',
      }),
    });

    final localStore = LocalAuthStore(
      baseUri: Uri.parse('http://127.0.0.1:8080'),
      apiKey: 'aijuris',
    );
    final devStore = LocalAuthStore(
      baseUri: Uri.parse('https://api-juris-dev.example.com'),
      apiKey: 'aijuris',
    );

    final localUser = await localStore.getCurrentUser();
    final devUser = await devStore.getCurrentUser();

    expect(localUser?.userId, 'local-user');
    expect(localUser?.email, 'local@example.com');
    expect(devUser?.userId, 'dev-user');
    expect(devUser?.email, 'dev@example.com');
  });

  test('sign out clears only the scoped current user', () async {
    SharedPreferences.setMockInitialValues({
      'mobile_auth_current_user_v3_http_127_0_0_1_8080': jsonEncode({
        'user_id': 'local-user',
        'phone_number': '+421900000001',
        'email': 'local@example.com',
        'password': 'local-pass',
      }),
      'mobile_auth_current_user_v3_https_api_juris_dev_example_com': jsonEncode({
        'user_id': 'dev-user',
        'phone_number': '+421900000002',
        'email': 'dev@example.com',
        'password': 'dev-pass',
      }),
    });

    final localStore = LocalAuthStore(
      baseUri: Uri.parse('http://127.0.0.1:8080'),
      apiKey: 'aijuris',
    );
    final devStore = LocalAuthStore(
      baseUri: Uri.parse('https://api-juris-dev.example.com'),
      apiKey: 'aijuris',
    );

    await localStore.signOut();

    expect(await localStore.getCurrentUser(), isNull);
    expect((await devStore.getCurrentUser())?.userId, 'dev-user');
  });

  test('sign out clears scoped device token metadata', () async {
    SharedPreferences.setMockInitialValues({
      'mobile_auth_device_token_v1_http_127_0_0_1_8080': 'token-local',
      'mobile_auth_device_token_issued_at_v1_http_127_0_0_1_8080':
          DateTime.utc(2026, 1, 1).millisecondsSinceEpoch,
      'mobile_auth_device_token_v1_https_api_juris_dev_example_com':
          'token-dev',
      'mobile_auth_device_token_issued_at_v1_https_api_juris_dev_example_com':
          DateTime.utc(2026, 1, 1).millisecondsSinceEpoch,
    });

    final localStore = LocalAuthStore(
      baseUri: Uri.parse('http://127.0.0.1:8080'),
      apiKey: 'aijuris',
    );
    final devStore = LocalAuthStore(
      baseUri: Uri.parse('https://api-juris-dev.example.com'),
      apiKey: 'aijuris',
    );

    await localStore.signOut();

    final prefs = await SharedPreferences.getInstance();
    expect(
      prefs.getString('mobile_auth_device_token_v1_http_127_0_0_1_8080'),
      isNull,
    );
    expect(
      prefs.getInt('mobile_auth_device_token_issued_at_v1_http_127_0_0_1_8080'),
      isNull,
    );
    expect(
      prefs.getString(
        'mobile_auth_device_token_v1_https_api_juris_dev_example_com',
      ),
      'token-dev',
    );
    expect(
      prefs.getInt(
        'mobile_auth_device_token_issued_at_v1_https_api_juris_dev_example_com',
      ),
      DateTime.utc(2026, 1, 1).millisecondsSinceEpoch,
    );

    expect((await devStore.getCurrentUser()), isNull);
  });

}
