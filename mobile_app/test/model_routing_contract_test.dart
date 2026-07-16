import 'dart:convert';
import 'dart:io';

import 'package:ai_jurisdiction_mobile/app/app_locale.dart';
import 'package:ai_jurisdiction_mobile/logging/app_logger_stub.dart';
import 'package:ai_jurisdiction_mobile/main.dart' as app;
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('mobile chat payloads leave model routing to the backend', () async {
    final requests = <Map<String, Object?>>[];
    final server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
    final serverDone = server.listen((request) async {
      final body = await utf8.decoder.bind(request).join();
      final decoded = body.trim().isEmpty
          ? <String, Object?>{}
          : jsonDecode(body) as Map<String, Object?>;
      requests.add(<String, Object?>{
        'method': request.method,
        'path': request.uri.path,
        'body': decoded,
      });
      request.response.headers.contentType = ContentType.json;
      if (request.uri.path == '/v1/chat/sessions') {
        request.response.write(jsonEncode(<String, Object?>{
          'id': 'session-mobile-routing',
          'user_id': decoded['user_id'],
          'case_id': decoded['case_id'],
          'country': decoded['country'],
          'language': decoded['language'],
          'discussion_type': decoded['discussion_type'],
          'state': 'active',
          'created_at': '2026-07-13T12:00:00Z',
        }));
      } else if (request.uri.path == '/v1/chat/sessions/session-mobile-routing/reply') {
        request.response.write(jsonEncode(<String, Object?>{
          'id': 'message-mobile-routing',
          'session_id': 'session-mobile-routing',
          'role': 'assistant',
          'content': 'Backend-routed answer',
          'agent_name': 'AI Lawyer',
          'created_at': '2026-07-13T12:00:01Z',
        }));
      } else {
        request.response.statusCode = HttpStatus.notFound;
        request.response.write(jsonEncode(<String, Object?>{'detail': 'not found'}));
      }
      await request.response.close();
    });

    try {
      final client = app.ApiClient(
        baseUri: Uri.parse('http://${server.address.host}:${server.port}'),
        apiKey: 'aijuris',
        logger: NoopLogger(),
      );
      client.setSignedInUser('user-mobile-routing');
      client.setActiveCase('case-mobile-routing');

      final reply = await client.sendMessage(
        message: 'Please review the case.',
        responderMode: app.ResponderMode.aiUserSimulator,
        locale: appLocaleOptions.first,
      );

      expect(reply, 'Backend-routed answer');
      expect(requests, hasLength(2));
      expect(requests[0]['path'], '/v1/chat/sessions');
      expect(requests[1]['path'], '/v1/chat/sessions/session-mobile-routing/reply');
      expect(requests[0]['body'], isNot(containsPair('model_profile_id', anything)));
      expect(requests[1]['body'], isNot(containsPair('model_profile_id', anything)));
      expect(requests[0]['body'], containsPair('user_id', 'user-mobile-routing'));
      expect(requests[0]['body'], containsPair('case_id', 'case-mobile-routing'));
    } finally {
      await server.close(force: true);
      await serverDone.cancel();
    }
  });
}
