-- Same schema applied idempotently by ApiDatabaseStore for local and PostgreSQL runtimes.
CREATE TABLE IF NOT EXISTS software_assessments (
    assessment_id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES cases(case_id) ON DELETE CASCADE,
    revision INTEGER NOT NULL DEFAULT 1,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS software_assessment_documents (
    assessment_id TEXT NOT NULL REFERENCES software_assessments(assessment_id) ON DELETE CASCADE,
    doc_id TEXT NOT NULL REFERENCES case_documents(doc_id) ON DELETE CASCADE,
    PRIMARY KEY(assessment_id, doc_id)
);
