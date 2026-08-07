ALTER TABLE court_decision_documents
ADD COLUMN IF NOT EXISTS issue_date_normalized DATE;

ALTER TABLE court_decision_documents
ADD COLUMN IF NOT EXISTS court_name_normalized TEXT NOT NULL DEFAULT '';

CREATE OR REPLACE FUNCTION pg_temp.safe_court_issue_date(value TEXT)
RETURNS DATE
LANGUAGE plpgsql
AS $$
DECLARE
    candidate DATE;
BEGIN
    IF BTRIM(COALESCE(value, '')) ~ '^\d{4}-\d{2}-\d{2}$' THEN
        RETURN BTRIM(value)::DATE;
    END IF;
    IF BTRIM(COALESCE(value, '')) ~ '^\d{2}\.\d{2}\.\d{4}$' THEN
        candidate := TO_DATE(BTRIM(value), 'DD.MM.YYYY');
        IF TO_CHAR(candidate, 'DD.MM.YYYY') = BTRIM(value) THEN
            RETURN candidate;
        END IF;
    END IF;
    RETURN NULL;
EXCEPTION WHEN datetime_field_overflow OR invalid_datetime_format THEN
    RETURN NULL;
END;
$$;

WITH latest_versions AS (
    SELECT DISTINCT ON (decision_id)
        decision_id,
        NULLIF(metadata_json -> 'povodnySud' ->> 'nazov', '') AS original_court_name
    FROM court_decision_versions
    ORDER BY decision_id, stored_at DESC
)
UPDATE court_decision_documents AS documents
SET court_name = latest_versions.original_court_name
FROM latest_versions
WHERE latest_versions.decision_id = documents.decision_id
  AND latest_versions.original_court_name IS NOT NULL
  AND documents.court_name IS DISTINCT FROM latest_versions.original_court_name;

UPDATE court_decision_documents
SET issue_date_normalized = pg_temp.safe_court_issue_date(issue_date),
    court_name_normalized = BTRIM(REGEXP_REPLACE(
        TRANSLATE(
            LOWER(court_name),
            'áäčďéěíĺľňóôöŕšťúüýž',
            'aacdeeillnooorstuuyz'
        ),
        '[^a-z0-9]+',
        ' ',
        'g'
    ));

CREATE INDEX IF NOT EXISTS idx_court_decision_documents_issue_date_normalized
ON court_decision_documents(issue_date_normalized);

CREATE INDEX IF NOT EXISTS idx_court_decision_documents_status_issue_date_normalized
ON court_decision_documents(current_status, issue_date_normalized DESC, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_court_decision_documents_court_name_normalized
ON court_decision_documents(court_name_normalized);

-- Validation after deployment:
-- SELECT COUNT(*) FILTER (WHERE issue_date_normalized IS NOT NULL) AS parsed,
--        COUNT(*) FILTER (WHERE issue_date <> '' AND issue_date_normalized IS NULL) AS invalid,
--        COUNT(*) FILTER (WHERE issue_date = '') AS missing
-- FROM court_decision_documents;
-- Rollback: drop the three *_normalized indexes, then drop the two added columns.
