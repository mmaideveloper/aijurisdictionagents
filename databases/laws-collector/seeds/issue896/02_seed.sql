INSERT INTO law_documents (
    document_id, country_code, collection_code, law_year, law_number,
    official_name, lawyer_title, source_url, publication_date, current_status,
    first_effective_date, applicable_to, first_stored_at, last_stored_at,
    last_checked_at, last_download_status, last_download_error,
    download_attempt_count, created_at, updated_at
) VALUES (
    %s, 'SK', 'ZZ', 2016, 679, %s, %s,
    'https://eur-lex.europa.eu/eli/reg/2016/679/oj',
    '2016-06-04', 'published', '2026-01-01',
    'Synthetic E2E software security fixture; not actual legislation.',
    %s, %s, %s, 'stored', '', 1, %s, %s
)

