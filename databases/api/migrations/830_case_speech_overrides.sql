CREATE TABLE IF NOT EXISTS case_speech_overrides (
    case_id TEXT PRIMARY KEY REFERENCES cases(case_id) ON DELETE CASCADE,
    model_profile_id TEXT NOT NULL REFERENCES ai_model_profiles(model_profile_id)
);
