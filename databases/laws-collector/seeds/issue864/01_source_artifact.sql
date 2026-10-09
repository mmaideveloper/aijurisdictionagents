-- Task-isolated synthetic source for the direct API and citation checks.
-- searchLaws uses metadata identifiers as well as the numeric document fields.
INSERT INTO law_metadata (
    law_metadata_id, document_id, version_id, law_identifier_text, title,
    law_type, publication_date, effective_from, legal_areas_json, metadata_json,
    created_at, updated_at
)
SELECT 'issue-864-law-metadata', d.document_id, v.version_id, '40/1964',
       d.official_name, 'synthetic', '1964-03-05', v.effective_from,
       '["synthetic-e2e"]'::jsonb, '{"synthetic":true}'::jsonb, v.stored_at, v.stored_at
FROM law_documents d JOIN law_versions v ON v.document_id = d.document_id
WHERE v.version_id = 'issue-635-civil-code-v1'
ON CONFLICT (version_id) DO UPDATE SET law_identifier_text = EXCLUDED.law_identifier_text;

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
