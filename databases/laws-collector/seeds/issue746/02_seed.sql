INSERT INTO law_documents (
    document_id, country_code, collection_code, law_year, law_number,
    official_name, lawyer_title, source_url, publication_date, current_status,
    first_effective_date, applicable_to, first_stored_at, last_stored_at,
    last_checked_at, last_download_status, last_download_error,
    download_attempt_count, created_at, updated_at
) VALUES (
    %s, 'SK', 'ZZ', 2003, 190, %s, %s,
    'https://static.slov-lex.sk/static/SK/ZZ/2003/190/20250701.html',
    '2003-06-04', 'published', '2025-07-01',
    'Verejný text zákona o strelných zbraniach a strelive v izolovanej E2E databáze.',
    %s, %s, %s, 'stored', '', 1, %s, %s
)
