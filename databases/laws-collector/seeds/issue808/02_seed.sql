INSERT INTO law_documents (
    document_id, country_code, collection_code, law_year, law_number,
    official_name, lawyer_title, source_url, publication_date, current_status,
    first_effective_date, applicable_to, first_stored_at, last_stored_at,
    last_checked_at, last_download_status, last_download_error,
    download_attempt_count, created_at, updated_at
) VALUES (
    %s, 'SK', 'ZZ', 2026, 808, %s, %s,
    'https://static.slov-lex.sk/static/SK/ZZ/2026/808/20260829.html',
    '2026-08-29', 'published', '2026-08-30',
    'Syntetický E2E predpis upravuje transparentnosť, auditné záznamy a ľudský dohľad pri testovaní právnych AI asistentov.',
    %s, %s, %s, 'stored', '', 1, %s, %s
)
