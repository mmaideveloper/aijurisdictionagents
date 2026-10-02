INSERT INTO law_metadata (
    law_metadata_id, document_id, version_id, law_identifier_text,
    title, law_type, approval_date, publication_date, effective_from,
    author, issue_reference, legal_areas_json, metadata_json,
    created_at, updated_at
) VALUES (
    'issue-746-metadata-v1', %s, 'issue-746-public-law-v1', %s,
    %s, 'zakon', '2003-04-23', '2003-06-04', '2025-07-01',
    'Národná rada Slovenskej republiky', 'issue-746', '["Strelné zbrane a strelivo"]',
    '{"synthetic": true}', %s, %s
)
