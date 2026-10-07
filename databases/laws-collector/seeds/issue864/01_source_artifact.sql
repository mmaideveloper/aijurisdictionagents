-- Task-isolated synthetic source for the direct API and citation checks.
INSERT INTO source_artifacts (
    artifact_id, document_id, version_id, source_system, artifact_kind,
    source_url, checksum, content_text, content_blob, content_bytes,
    http_etag, http_last_modified, should_redownload, verification_status,
    download_error, fetched_at, last_checked_at
)
SELECT
    'issue-864-source-html', v.document_id, v.version_id, 'synthetic-e2e', 'html',
    d.source_url, 'issue864synthetic', p.body_text, NULL, OCTET_LENGTH(p.body_text),
    '', '', FALSE, 'synthetic_verified', '', v.stored_at, v.stored_at
FROM law_versions v
JOIN law_documents d ON d.document_id = v.document_id
JOIN law_provisions p ON p.version_id = v.version_id
WHERE v.version_id = 'issue-635-civil-code-v1'
  AND p.provision_id = 'issue-635-provision-569'
ON CONFLICT (artifact_id) DO UPDATE SET content_text = EXCLUDED.content_text;
