-- No grandfathered access: existing sessions must obtain explicit bank grants.
ALTER TABLE test_definitions ADD COLUMN description text NOT NULL DEFAULT '';
ALTER TABLE test_definitions ADD COLUMN subject text NOT NULL DEFAULT '';
ALTER TABLE test_definitions ADD COLUMN starts_at timestamptz;
ALTER TABLE test_definitions ADD COLUMN bank_tags jsonb NOT NULL DEFAULT '[]';
ALTER TABLE test_definitions DROP CONSTRAINT publication_review;
ALTER TABLE test_definitions ADD CONSTRAINT publication_review CHECK (
 status <> 'published' OR (
  (subject IN ('biology','chemistry') OR legal_date IS NOT NULL)
  AND reviewed_at IS NOT NULL AND reviewed_by IS NOT NULL AND length(trim(reviewed_by))>0
  AND rights_confirmed AND jsonb_typeof(source_links)='array' AND jsonb_array_length(source_links)>0
 )
);
ALTER TABLE questions ADD COLUMN enabled boolean NOT NULL DEFAULT true;
ALTER TABLE questions ADD COLUMN revision integer NOT NULL DEFAULT 1;
ALTER TABLE questions ADD COLUMN tags jsonb NOT NULL DEFAULT '[]';
ALTER TABLE questions ADD COLUMN options jsonb NOT NULL DEFAULT '[]';
ALTER TABLE questions ADD COLUMN related_ids jsonb NOT NULL DEFAULT '[]';
ALTER TABLE questions ADD CONSTRAINT question_tags_array CHECK(jsonb_typeof(tags)='array');
CREATE TABLE test_users (
 user_id text PRIMARY KEY, approved boolean NOT NULL DEFAULT false,
 updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE bank_access (
 user_id text NOT NULL REFERENCES test_users(user_id) ON DELETE CASCADE,
 test_id text NOT NULL REFERENCES test_definitions(id),
 status text NOT NULL CHECK(status IN ('pending','approved','rejected','revoked')),
 updated_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY(user_id,test_id)
);
CREATE TABLE question_revisions (
 question_id text NOT NULL REFERENCES questions(id), revision integer NOT NULL,
 snapshot jsonb NOT NULL, actor_id text NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(question_id,revision)
);
CREATE TABLE study_sets (
 id uuid PRIMARY KEY, user_id text NOT NULL, test_id text NOT NULL REFERENCES test_definitions(id),
 name text NOT NULL CHECK(length(trim(name)) BETWEEN 1 AND 120),
 question_ids jsonb NOT NULL, updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE bank_jobs (
 id uuid PRIMARY KEY, test_id text NOT NULL REFERENCES test_definitions(id), actor_id text NOT NULL,
 kind text NOT NULL CHECK(kind IN ('import','tagging')),
 status text NOT NULL CHECK(status IN ('queued','running','review','error','cancelled','applied')),
 payload jsonb NOT NULL, result jsonb NOT NULL DEFAULT '[]',
 cursor integer NOT NULL DEFAULT 0, total integer NOT NULL DEFAULT 0,
 error_code text, lease_until timestamptz, lease_token uuid,
 provider text NOT NULL DEFAULT 'azurefoundry', model text NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX bank_jobs_queue ON bank_jobs(status,created_at);
CREATE TABLE bank_audit (
 id uuid PRIMARY KEY, actor_id text NOT NULL, action text NOT NULL,
 target_id text NOT NULL, created_at timestamptz NOT NULL DEFAULT now()
);
-- Medical titles are drafts; no purchased questions or implied faculty endorsement.
INSERT INTO test_definitions(id,name,version,status,categories,description,subject)
VALUES ('lfuk-biology','LF UK Bratislava — biológia','1','draft','["biology"]',
 'Nezávislá príprava na prijímacie skúšky. Obsah čaká na import a kontrolu.','biology'),
 ('lfuk-chemistry','LF UK Bratislava — chémia','1','draft','["chemistry"]',
 'Nezávislá príprava na prijímacie skúšky. Obsah čaká na import a kontrolu.','chemistry')
ON CONFLICT(id) DO NOTHING;
