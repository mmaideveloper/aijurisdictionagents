import 'dart:convert';
import 'dart:math';

import '../update/github_release.dart';

class MobileAppUpdateInfo {
  const MobileAppUpdateInfo({
    required this.version,
    required this.releaseUrl,
    required this.apkDownloadUrl,
  });

  final SemanticVersion version;
  final String releaseUrl;
  final String? apkDownloadUrl;
}

class ApiSystemVersionInfo {
  const ApiSystemVersionInfo({
    required this.countryCode,
    required this.lastLawUpdateDate,
    required this.modelKnowledgeCutoffDate,
  });

  final String countryCode;
  final String? lastLawUpdateDate;
  final String? modelKnowledgeCutoffDate;
}

class ApiHealthCheckResult {
  const ApiHealthCheckResult._({
    required this.isHealthy,
    this.errorMessage,
    this.isNetworkError = false,
    this.isOfflineError = false,
  });

  const ApiHealthCheckResult.healthy()
      : this._(
          isHealthy: true,
        );

  const ApiHealthCheckResult.unhealthy({
    required this.errorMessage,
    required this.isNetworkError,
    this.isOfflineError = false,
  }) : isHealthy = false;

  final bool isHealthy;
  final String? errorMessage;
  final bool isNetworkError;
  final bool isOfflineError;
}

bool isLikelyOfflineError(Object? error) {
  final normalized = '${error ?? ''}'.toLowerCase();
  return normalized.contains('socketexception') ||
      normalized.contains('failed host lookup') ||
      normalized.contains('network is unreachable') ||
      normalized.contains('network is down') ||
      normalized.contains('temporary failure in name resolution') ||
      normalized.contains('no address associated with hostname');
}

ApiHealthCheckResult parseApiHealthCheckResult({
  required int statusCode,
  required String responseBody,
}) {
  Map<String, dynamic>? payload;
  try {
    final decoded = jsonDecode(responseBody);
    if (decoded is Map<String, dynamic>) {
      payload = decoded;
    } else if (decoded is Map) {
      payload = Map<String, dynamic>.from(decoded);
    }
  } catch (_) {}

  final message = (payload?['message'] as String? ?? '').trim();
  final error = (payload?['error'] as String? ?? '').trim();
  final status = (payload?['status'] as String? ?? '').trim().toLowerCase();
  final databasePayload = payload?['database'];
  final databaseStatus = databasePayload is Map
      ? (databasePayload['status'] as String? ?? '').trim().toLowerCase()
      : '';

  if (statusCode < 200 || statusCode >= 300) {
    if (message.isNotEmpty) {
      return ApiHealthCheckResult.unhealthy(
        errorMessage: message,
        isNetworkError: false,
        isOfflineError: false,
      );
    }
    if (error.isNotEmpty) {
      return ApiHealthCheckResult.unhealthy(
        errorMessage: 'Health check failed: $error.',
        isNetworkError: false,
        isOfflineError: false,
      );
    }
    return ApiHealthCheckResult.unhealthy(
      errorMessage: 'Health check failed with status $statusCode.',
      isNetworkError: false,
      isOfflineError: false,
    );
  }

  if (status.isNotEmpty && status != 'ok') {
    return ApiHealthCheckResult.unhealthy(
      errorMessage: message.isNotEmpty
          ? message
          : 'Health endpoint returned status "$status".',
      isNetworkError: false,
      isOfflineError: false,
    );
  }

  if (databaseStatus.isNotEmpty && databaseStatus != 'ok') {
    return ApiHealthCheckResult.unhealthy(
      errorMessage: message.isNotEmpty
          ? message
          : 'Database health check reported status "$databaseStatus".',
      isNetworkError: false,
      isOfflineError: false,
    );
  }

  return const ApiHealthCheckResult.healthy();
}

int apiHealthRetryDelaySeconds(int failureCount) {
  final normalizedFailureCount = max(0, failureCount);
  final doubled = 1 << (normalizedFailureCount + 1);
  return min(16, doubled);
}
