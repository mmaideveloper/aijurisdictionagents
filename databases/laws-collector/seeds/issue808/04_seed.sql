INSERT INTO law_metadata (
    law_metadata_id, document_id, version_id, law_identifier_text,
    title, law_type, approval_date, publication_date, effective_from,
    author, issue_reference, legal_areas_json, metadata_json,
    created_at, updated_at
) VALUES (
    'issue-808-metadata-v1', %s, 'issue-808-prompt-boundary-v1', %s,
    %s, 'synthetic_e2e', '2026-08-28', '2026-08-29', '2026-08-30',
    'Syntetický zákonodarca', 'issue-808', '["AI governance"]',
    '{"synthetic": true}', %s, %s
)
