INSERT INTO law_metadata (
    law_metadata_id, document_id, version_id, law_identifier_text,
    title, law_type, approval_date, publication_date, effective_from,
    author, issue_reference, legal_areas_json, metadata_json,
    created_at, updated_at
) VALUES (
    'issue-896-metadata-v1', %s, 'issue-896-public-law-v1', %s,
    %s, 'zakon', '2016-04-23', '2016-06-04', '2026-01-01',
    'Národná rada Slovenskej republiky', 'issue-896', '["Synthetic software security GDPR"]',
    '{"synthetic": true}', %s, %s
)

