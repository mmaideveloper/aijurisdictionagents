CREATE INDEX IF NOT EXISTS idx_court_decision_enrichments_search
ON court_decision_enrichments USING GIN (
    to_tsvector(
        'simple'::regconfig,
        pseudonymized_summary || ' ' || pseudonymized_text || ' ' || legal_topics::text
    )
)
WHERE status = 'ready';

CREATE INDEX IF NOT EXISTS idx_court_decision_content_chunks_search
ON court_decision_content_chunks USING GIN (
    to_tsvector('simple'::regconfig, pseudonymized_text)
);
