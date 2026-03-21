import 'package:ai_jurisdiction_mobile/update/github_release.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('SemanticVersion', () {
    test('parses versions with build number', () {
      final version = SemanticVersion.tryParse('v0.1.2+4');

      expect(version, isNotNull);
      expect(version.toString(), '0.1.2+4');
    });

    test('compares build number after major minor patch', () {
      const older = SemanticVersion(major: 0, minor: 1, patch: 2, build: 3);
      const newer = SemanticVersion(major: 0, minor: 1, patch: 2, build: 4);

      expect(older.compareTo(newer), lessThan(0));
    });
  });

  group('parseGithubReleaseInfo', () {
    test('prefers app-release.apk asset when available', () {
      final release = parseGithubReleaseInfo(<String, dynamic>{
        'tag_name': '0.1.2',
        'html_url': 'https://github.com/example/release',
        'assets': <Map<String, String>>[
          <String, String>{
            'name': 'other.apk',
            'browser_download_url': 'https://example.invalid/other.apk',
          },
          <String, String>{
            'name': 'app-release.apk',
            'browser_download_url': 'https://example.invalid/app-release.apk',
          },
        ],
      });

      expect(release, isNotNull);
      expect(release!.version.toString(), '0.1.2');
      expect(
        release.apkDownloadUrl,
        'https://example.invalid/app-release.apk',
      );
    });

    test('returns null when release tag is not semantic version', () {
      final release = parseGithubReleaseInfo(<String, dynamic>{
        'tag_name': 'release-xyz',
        'html_url': 'https://github.com/example/release',
        'assets': const <Object>[],
      });

      expect(release, isNull);
    });
  });

  group('parseGithubReleaseResponseBody', () {
    test('parses a valid GitHub latest release payload', () {
      final release = parseGithubReleaseResponseBody('''
{
  "tag_name": "v0.1.5+29",
  "html_url": "https://github.com/mmaideveloper/aijurisdictionagents/releases/tag/v0.1.5+29",
  "assets": [
    {
      "name": "app-release.apk",
      "browser_download_url": "https://example.invalid/app-release.apk"
    }
  ]
}
''');

      expect(release, isNotNull);
      expect(release!.version.toString(), '0.1.5+29');
      expect(
        release.apkDownloadUrl,
        'https://example.invalid/app-release.apk',
      );
    });
  });

  group('githubLatestReleaseApiUriFromReleaseUrl', () {
    test('derives the GitHub API latest-release endpoint', () {
      final uri = githubLatestReleaseApiUriFromReleaseUrl(
        'https://github.com/mmaideveloper/aijurisdictionagents/releases/latest',
      );

      expect(
        uri?.toString(),
        'https://api.github.com/repos/mmaideveloper/aijurisdictionagents/releases/latest',
      );
    });

    test('returns null for non-GitHub release URLs', () {
      final uri = githubLatestReleaseApiUriFromReleaseUrl(
        'https://example.invalid/releases/latest',
      );

      expect(uri, isNull);
    });
  });
}
