CREATE TABLE IF NOT EXISTS collector_progress (
    country_code TEXT PRIMARY KEY,
    source_system TEXT NOT NULL,
    last_collector_run_at TIMESTAMPTZ,
    last_processed_at TIMESTAMPTZ,
    last_processed_law_year INTEGER,
    last_processed_law_number INTEGER,
    next_probe_law_year INTEGER NOT NULL,
    next_probe_law_number INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);
