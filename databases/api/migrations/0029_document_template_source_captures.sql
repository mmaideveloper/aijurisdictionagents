CREATE TABLE IF NOT EXISTS document_template_source_captures (
    template_key TEXT NOT NULL,
    source_url TEXT NOT NULL,
    captured_at TEXT NOT NULL,
    content_sha256 TEXT NOT NULL DEFAULT '',
    artifact_reference TEXT NOT NULL DEFAULT '',
    capture_status TEXT NOT NULL,
    failure_code TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (template_key, source_url)
);
