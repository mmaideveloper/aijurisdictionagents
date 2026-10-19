CREATE TABLE IF NOT EXISTS case_file_migration_journal (
    migration_id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL,
    payload TEXT NOT NULL
);
