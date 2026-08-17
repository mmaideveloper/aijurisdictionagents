ALTER TABLE ai_model_providers
    ADD COLUMN IF NOT EXISTS model_parameters_json TEXT NOT NULL DEFAULT '{}';

ALTER TABLE ai_model_profiles
    ADD COLUMN IF NOT EXISTS model_parameters_json TEXT NOT NULL DEFAULT '{}';

COMMENT ON COLUMN ai_model_providers.model_parameters_json IS
    'Validated non-secret provider request defaults. Model profile values override these defaults.';

COMMENT ON COLUMN ai_model_profiles.model_parameters_json IS
    'Validated non-secret request parameters for this model/deployment profile.';
