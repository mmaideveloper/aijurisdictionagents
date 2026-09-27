ALTER TABLE test_definitions ADD COLUMN source_links jsonb NOT NULL DEFAULT '[]';
ALTER TABLE test_definitions ADD COLUMN category_labels jsonb NOT NULL DEFAULT '{}';
ALTER TABLE test_definitions ADD COLUMN legal_summary text NOT NULL DEFAULT '';
ALTER TABLE test_definitions ADD COLUMN case_type text NOT NULL DEFAULT 'KNOWLEDGE_TEST';
ALTER TABLE test_definitions ADD COLUMN reviewed_by text;
ALTER TABLE test_definitions ADD COLUMN reviewed_at timestamptz;
ALTER TABLE test_definitions ADD COLUMN rights_confirmed boolean NOT NULL DEFAULT false;
ALTER TABLE test_definitions ADD CONSTRAINT publication_review CHECK (
  status <> 'published' OR (
    legal_date IS NOT NULL AND reviewed_at IS NOT NULL AND length(trim(reviewed_by)) > 0
    AND reviewed_by IS NOT NULL AND rights_confirmed
    AND jsonb_typeof(source_links) = 'array' AND jsonb_array_length(source_links) > 0
  )
);
ALTER TABLE test_definitions ADD CONSTRAINT category_arrays CHECK (
  jsonb_typeof(categories)='array' AND jsonb_array_length(categories)>0
  AND jsonb_typeof(exam_categories)='array' AND categories @> exam_categories
);
