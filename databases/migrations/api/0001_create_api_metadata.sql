CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,
    phone_number TEXT UNIQUE,
    email TEXT UNIQUE NOT NULL,
    first_name TEXT,
    last_name TEXT,
    full_name TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    created_at TEXT NOT NULL
);

ALTER TABLE users ADD COLUMN IF NOT EXISTS phone_number TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS first_name TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS last_name TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS idx_users_phone_number
ON users(phone_number)
WHERE phone_number IS NOT NULL;

UPDATE users
SET full_name = COALESCE(NULLIF(TRIM(full_name), ''), email)
WHERE full_name IS NULL OR TRIM(full_name) = '';

CREATE TABLE IF NOT EXISTS companies (
    company_id TEXT PRIMARY KEY,
    legal_name TEXT NOT NULL,
    profile_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS company_users (
    company_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    role TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY(company_id, user_id)
);

CREATE TABLE IF NOT EXISTS cases (
    case_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    company_id TEXT,
    title TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_cases_user_id_updated_at
ON cases(user_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS case_documents (
    doc_id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    version INTEGER NOT NULL,
    storage_uri TEXT NOT NULL,
    original_filename TEXT NOT NULL,
    uploaded_by_user_id TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_case_documents_case_created_at
ON case_documents(case_id, created_at DESC);

CREATE TABLE IF NOT EXISTS case_communications (
    communication_id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL,
    channel TEXT NOT NULL,
    transcript_uri TEXT,
    summary TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_case_communications_case_created_at
ON case_communications(case_id, created_at DESC);
