import 'package:ai_jurisdiction_mobile/main.dart' as app;
import 'package:flutter/foundation.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('defaultApiBaseUrlForEnvironment', () {
    test('uses override when provided', () {
      expect(
        app.defaultApiBaseUrlForEnvironment(
          override: ' https://api.example.test ',
          isWeb: false,
          targetPlatform: TargetPlatform.android,
        ),
        'https://api.example.test',
      );
    });

    test('normalizes local https overrides to http', () {
      expect(
        app.defaultApiBaseUrlForEnvironment(
          override: 'https://127.0.0.1:8080',
          isWeb: true,
          targetPlatform: TargetPlatform.windows,
        ),
        'http://127.0.0.1:8080',
      );
      expect(
        app.defaultApiBaseUrlForEnvironment(
          override: 'https://localhost:8080',
          isWeb: true,
          targetPlatform: TargetPlatform.windows,
        ),
        'http://localhost:8080',
      );
      expect(
        app.defaultApiBaseUrlForEnvironment(
          override: 'https://api.jurisdigta.eu',
          isWeb: true,
          targetPlatform: TargetPlatform.windows,
        ),
        'https://api.jurisdigta.eu',
      );
    });

    test('uses Android emulator gateway only for Android', () {
      expect(
        app.defaultApiBaseUrlForEnvironment(
          override: '',
          isWeb: false,
          targetPlatform: TargetPlatform.android,
        ),
        'http://10.0.2.2:8080',
      );
    });

    test('uses localhost for web and desktop platforms', () {
      expect(
        app.defaultApiBaseUrlForEnvironment(
          override: '',
          isWeb: true,
          targetPlatform: TargetPlatform.android,
        ),
        'http://127.0.0.1:8080',
      );
      expect(
        app.defaultApiBaseUrlForEnvironment(
          override: '',
          isWeb: false,
          targetPlatform: TargetPlatform.windows,
        ),
        'http://127.0.0.1:8080',
      );
    });
  });

  group('API error messages', () {
    test('has a separate assistant stream failure message', () {
      final strings = app.AppStrings('SK');

      expect(
        strings.t(
          'assistant_response_failed_with_correlation',
          <String, String>{'id': 'mbl-flow-test'},
        ),
        contains('API je dostupné'),
      );
      expect(
        strings.t(
          'assistant_response_failed_with_correlation',
          <String, String>{'id': 'mbl-flow-test'},
        ),
        isNot(contains('Nepodarilo sa spojiť')),
      );
    });

    test('stream exceptions preserve sanitized operation context', () {
      final error = app.ApiStreamException.fromEvent(
        'ReadUser',
        <String, Object?>{'message': 'model timeout'},
      );

      expect(error.toString(), contains('ReadUser stream reported error'));
      expect(error.toString(), contains('model timeout'));
    });
  });
}
