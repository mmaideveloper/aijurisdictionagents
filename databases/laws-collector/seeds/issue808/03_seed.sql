INSERT INTO law_versions (
    version_id, document_id, version_token, effective_from, version_checksum,
    status, html_checksum, pdf_checksum, html_bytes, pdf_bytes,
    normalized_json, embedding_vector, stored_at, created_at, updated_at,
    embedding_model, embedding_dimensions
) VALUES (
    'issue-808-prompt-boundary-v1', %s, 'e2e-v1', '2026-08-30',
    'issue808checksum', 'active', 'html808', 'pdf808', 256, 0,
    '{"synthetic": true}', '[0,0,0,0,0,0,0,0]', %s, %s, %s,
    'deterministic-legacy-8d', 8
)
