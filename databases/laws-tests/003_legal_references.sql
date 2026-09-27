-- Editorial annotations disambiguate bare provision references. Original text stays intact.
ALTER TABLE questions ADD COLUMN legal_references jsonb NOT NULL DEFAULT '[]'
    CHECK (jsonb_typeof(legal_references) = 'array');
ALTER TABLE subquestions ADD COLUMN legal_references jsonb NOT NULL DEFAULT '[]'
    CHECK (jsonb_typeof(legal_references) = 'array');
