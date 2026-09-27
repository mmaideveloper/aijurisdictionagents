CREATE TABLE IF NOT EXISTS test_definitions (
    id text PRIMARY KEY,
    name text NOT NULL,
    version text NOT NULL,
    legal_date date,
    status text NOT NULL CHECK (status IN ('draft','development','published','withdrawn')),
    expires_at timestamptz,
    categories jsonb NOT NULL DEFAULT '[]',
    exam_categories jsonb NOT NULL DEFAULT '[]',
    aggregation text NOT NULL DEFAULT 'mean' CHECK (aggregation IN ('mean','minimum')),
    UNIQUE(id, version)
);
CREATE TABLE IF NOT EXISTS questions (
    id text PRIMARY KEY,
    test_id text NOT NULL REFERENCES test_definitions(id),
    category text NOT NULL,
    number integer NOT NULL CHECK (number > 0),
    title text NOT NULL,
    body text NOT NULL,
    structure text NOT NULL CHECK (structure IN ('direct','grouped')),
    answer text,
    rules jsonb NOT NULL DEFAULT '[]',
    provenance jsonb NOT NULL DEFAULT '[]',
    UNIQUE(test_id, category, number),
    UNIQUE(id, test_id),
    CHECK ((structure='direct' AND answer IS NOT NULL AND length(trim(answer))>0) OR (structure='grouped' AND answer IS NULL))
);
CREATE TABLE IF NOT EXISTS subquestions (
    id text PRIMARY KEY,
    question_id text NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
    sequence integer NOT NULL CHECK (sequence > 0),
    body text NOT NULL CHECK(length(trim(body))>0),
    answer text NOT NULL CHECK(length(trim(answer))>0),
    rules jsonb NOT NULL DEFAULT '[]',
    UNIQUE(question_id, sequence), UNIQUE(id, question_id)
);
CREATE OR REPLACE FUNCTION validate_question_structure() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF EXISTS (SELECT 1 FROM questions q WHERE
      (q.structure='direct' AND EXISTS(SELECT 1 FROM subquestions s WHERE s.question_id=q.id)) OR
      (q.structure='grouped' AND NOT EXISTS(SELECT 1 FROM subquestions s WHERE s.question_id=q.id))) THEN
      RAISE EXCEPTION 'Invalid direct/grouped question structure';
    END IF;
    IF EXISTS(SELECT 1 FROM test_definitions t WHERE t.status IN ('published','development')
      AND NOT EXISTS(SELECT 1 FROM questions q WHERE q.test_id=t.id)) THEN
      RAISE EXCEPTION 'Published tests require questions';
    END IF;
    RETURN NULL;
END $$;
CREATE CONSTRAINT TRIGGER questions_structure AFTER INSERT OR UPDATE OR DELETE ON questions
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION validate_question_structure();
CREATE CONSTRAINT TRIGGER subquestions_structure AFTER INSERT OR UPDATE OR DELETE ON subquestions
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION validate_question_structure();
CREATE CONSTRAINT TRIGGER tests_structure AFTER INSERT OR UPDATE ON test_definitions
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION validate_question_structure();
CREATE TABLE IF NOT EXISTS login_requests (
    state_hash text PRIMARY KEY, browser_hash text NOT NULL, code_hash text UNIQUE,
    user_id text, return_path text NOT NULL, expires_at timestamptz NOT NULL
);
CREATE TABLE IF NOT EXISTS web_sessions (
    token_hash text PRIMARY KEY, user_id text NOT NULL, csrf text NOT NULL,
    expires_at timestamptz NOT NULL
);
CREATE TABLE IF NOT EXISTS test_sessions (
    id uuid PRIMARY KEY, user_id text NOT NULL,
    test_id text NOT NULL REFERENCES test_definitions(id),
    mode text NOT NULL CHECK(mode IN ('learning','exam')),
    question_ids jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(id, user_id, test_id)
);
CREATE TABLE IF NOT EXISTS attempts (
    id uuid PRIMARY KEY, user_id text NOT NULL, test_id text NOT NULL,
    session_id uuid NOT NULL, question_id text NOT NULL, subquestion_id text,
    request_id uuid NOT NULL, content_snapshot jsonb NOT NULL,
    user_answer text NOT NULL CHECK(length(user_answer) BETWEEN 1 AND 12000),
    status text NOT NULL CHECK(status IN ('pending','completed','error')),
    score integer CHECK(score BETWEEN 0 AND 100), passed boolean,
    result jsonb, provider text NOT NULL, model text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(), evaluated_at timestamptz,
    UNIQUE(user_id, request_id),
    FOREIGN KEY (session_id,user_id,test_id) REFERENCES test_sessions(id,user_id,test_id) ON DELETE CASCADE,
    FOREIGN KEY (question_id,test_id) REFERENCES questions(id,test_id),
    FOREIGN KEY (subquestion_id,question_id) REFERENCES subquestions(id,question_id),
    CHECK ((status='completed' AND score IS NOT NULL AND passed=(score>=70) AND result IS NOT NULL)
        OR (status IN ('pending','error') AND score IS NULL AND passed IS NULL))
);
CREATE INDEX attempts_user ON attempts(user_id, created_at);
CREATE OR REPLACE FUNCTION validate_attempt_item() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM questions q WHERE q.id=NEW.question_id AND
     ((q.structure='direct' AND NEW.subquestion_id IS NULL) OR
      (q.structure='grouped' AND NEW.subquestion_id IS NOT NULL))) THEN
      RAISE EXCEPTION 'Attempt must target an answerable item';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER attempt_item BEFORE INSERT OR UPDATE ON attempts
FOR EACH ROW EXECUTE FUNCTION validate_attempt_item();
