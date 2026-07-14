CREATE INDEX IF NOT EXISTS idx_court_decision_documents_status_issue_date_normalized
ON court_decision_documents(current_status, issue_date_normalized DESC, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_court_decision_documents_metadata_search_text
ON court_decision_documents USING GIN (
    to_tsvector(
        'simple'::regconfig,
        COALESCE(court_name, '') || ' ' ||
        COALESCE(court_type, '') || ' ' ||
        COALESCE(file_number, '') || ' ' ||
        COALESCE(case_number, '') || ' ' ||
        COALESCE(ecli, '')
    )
);

CREATE INDEX IF NOT EXISTS idx_court_decision_versions_decision_stored_at
ON court_decision_versions(decision_id, stored_at DESC);

CREATE INDEX IF NOT EXISTS idx_court_decision_search_text
ON court_decision_versions USING GIN (
    to_tsvector('simple', pseudonymized_text)
);
