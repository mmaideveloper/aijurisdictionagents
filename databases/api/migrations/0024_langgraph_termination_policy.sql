ALTER TABLE case_workflow_runs
ADD COLUMN IF NOT EXISTS termination_reason TEXT NOT NULL DEFAULT '';
