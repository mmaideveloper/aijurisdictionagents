CREATE INDEX IF NOT EXISTS idx_court_decision_documents_status_issue_date
ON court_decision_documents(current_status, issue_date DESC, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_court_decision_documents_metadata_search_text
ON court_decision_documents USING GIN (
    to_tsvector(
        'simple',
        concat_ws(' ', court_name, court_type, file_number, case_number, ecli)
    )
);

CREATE INDEX IF NOT EXISTS idx_court_decision_versions_decision_stored_at
ON court_decision_versions(decision_id, stored_at DESC);

CREATE INDEX IF NOT EXISTS idx_court_decision_search_text
ON court_decision_versions USING GIN (
    to_tsvector('simple', pseudonymized_text)
);
