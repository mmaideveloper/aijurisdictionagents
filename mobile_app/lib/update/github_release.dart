import 'dart:convert';

class SemanticVersion implements Comparable<SemanticVersion> {
  const SemanticVersion({
    required this.major,
    required this.minor,
    required this.patch,
    required this.build,
  });

  final int major;
  final int minor;
  final int patch;
  final int build;

  static SemanticVersion? tryParse(String input) {
    final match = RegExp(r'(\d+)\.(\d+)\.(\d+)(?:\+(\d+))?').firstMatch(input);
    if (match == null) {
      return null;
    }
    return SemanticVersion(
      major: int.tryParse(match.group(1) ?? '') ?? 0,
      minor: int.tryParse(match.group(2) ?? '') ?? 0,
      patch: int.tryParse(match.group(3) ?? '') ?? 0,
      build: int.tryParse(match.group(4) ?? '') ?? 0,
    );
  }

  @override
  int compareTo(SemanticVersion other) {
    final majorDiff = major.compareTo(other.major);
    if (majorDiff != 0) {
      return majorDiff;
    }
    final minorDiff = minor.compareTo(other.minor);
    if (minorDiff != 0) {
      return minorDiff;
    }
    final patchDiff = patch.compareTo(other.patch);
    if (patchDiff != 0) {
      return patchDiff;
    }
    return build.compareTo(other.build);
  }

  @override
  String toString() {
    if (build > 0) {
      return '$major.$minor.$patch+$build';
    }
    return '$major.$minor.$patch';
  }
}

class GithubReleaseInfo {
  const GithubReleaseInfo({
    required this.tagName,
    required this.version,
    required this.releaseUrl,
    required this.apkDownloadUrl,
  });

  final String tagName;
  final SemanticVersion version;
  final String releaseUrl;
  final String? apkDownloadUrl;
}

GithubReleaseInfo? parseGithubReleaseInfo(Map<String, dynamic> payload) {
  final tagName = payload['tag_name'] as String? ?? '';
  final releaseUrl = payload['html_url'] as String? ?? '';
  final version = SemanticVersion.tryParse(tagName);
  if (version == null) {
    return null;
  }
  final assets = payload['assets'];
  return GithubReleaseInfo(
    tagName: tagName,
    version: version,
    releaseUrl: releaseUrl,
    apkDownloadUrl: pickGithubApkAssetDownloadUrl(assets),
  );
}

GithubReleaseInfo? parseGithubReleaseResponseBody(String responseBody) {
  try {
    final decoded = jsonDecode(responseBody);
    if (decoded is Map<String, dynamic>) {
      return parseGithubReleaseInfo(decoded);
    }
    if (decoded is Map) {
      return parseGithubReleaseInfo(Map<String, dynamic>.from(decoded));
    }
  } catch (_) {}
  return null;
}

Uri? githubLatestReleaseApiUriFromReleaseUrl(String releaseUrl) {
  final trimmed = releaseUrl.trim();
  if (trimmed.isEmpty) {
    return null;
  }
  final uri = Uri.tryParse(trimmed);
  if (uri == null || uri.host.toLowerCase() != 'github.com') {
    return null;
  }
  final segments =
      uri.pathSegments.where((segment) => segment.isNotEmpty).toList();
  if (segments.length < 4 || segments[2] != 'releases') {
    return null;
  }
  final owner = segments[0];
  final repo = segments[1];
  if (owner.isEmpty || repo.isEmpty) {
    return null;
  }
  return Uri.https(
    'api.github.com',
    '/repos/$owner/$repo/releases/latest',
  );
}

String? pickGithubApkAssetDownloadUrl(Object? assetsPayload) {
  if (assetsPayload is! List) {
    return null;
  }

  String? fallback;
  for (final asset in assetsPayload) {
    if (asset is! Map) {
      continue;
    }
    final rawName = asset['name'];
    final rawDownloadUrl = asset['browser_download_url'];
    if (rawName is! String || rawDownloadUrl is! String) {
      continue;
    }
    final assetName = rawName.trim().toLowerCase();
    final downloadUrl = rawDownloadUrl.trim();
    if (downloadUrl.isEmpty || !assetName.endsWith('.apk')) {
      continue;
    }
    if (assetName == 'app-release.apk') {
      return downloadUrl;
    }
    fallback ??= downloadUrl;
  }
  return fallback;
}
