INSERT INTO source_artifacts (
    artifact_id, document_id, version_id, source_system, artifact_kind,
    source_url, checksum, content_text, content_blob, content_bytes,
    http_etag, http_last_modified, should_redownload, verification_status,
    download_error, fetched_at, last_checked_at
) VALUES (
    'issue-746-source-html-v1', %s, 'issue-746-public-law-v1',
    'synthetic-e2e', 'html',
    'https://static.slov-lex.sk/static/SK/ZZ/2003/190/20250701.html',
    'issue746htmlchecksum', %s, NULL, %s, '', '', FALSE,
    'synthetic_verified', '', %s, %s
)
