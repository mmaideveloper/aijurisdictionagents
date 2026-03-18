import 'package:ai_jurisdiction_mobile/api/app_status.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('api health retry delay uses exponential backoff capped at 16 seconds',
      () {
    expect(apiHealthRetryDelaySeconds(0), 2);
    expect(apiHealthRetryDelaySeconds(1), 4);
    expect(apiHealthRetryDelaySeconds(2), 8);
    expect(apiHealthRetryDelaySeconds(3), 16);
    expect(apiHealthRetryDelaySeconds(4), 16);
  });

  test('api health parser accepts healthy database payload', () {
    final result = parseApiHealthCheckResult(
      statusCode: 200,
      responseBody:
          '{"status":"ok","database":{"status":"ok","backend":"azure"}}',
    );

    expect(result.isHealthy, isTrue);
    expect(result.errorMessage, isNull);
    expect(result.isNetworkError, isFalse);
  });

  test('api health parser returns API message for unhealthy database payload',
      () {
    final result = parseApiHealthCheckResult(
      statusCode: 503,
      responseBody:
          '{"status":"error","error":"database_unavailable","message":"Database health check failed for backend \\"azure\\": password authentication failed","database":{"status":"error","backend":"azure"}}',
    );

    expect(result.isHealthy, isFalse);
    expect(
      result.errorMessage,
      'Database health check failed for backend "azure": password authentication failed',
    );
    expect(result.isNetworkError, isFalse);
  });
}
