-- Retain missing/transient work without allowing it to monopolize the queue.
ALTER TABLE court_decision_import_queue
ADD COLUMN IF NOT EXISTS next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT 'epoch';
