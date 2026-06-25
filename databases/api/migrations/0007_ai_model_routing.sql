CREATE TABLE IF NOT EXISTS ai_model_providers (
    provider_id TEXT PRIMARY KEY,
    provider_code TEXT UNIQUE NOT NULL,
    provider_type TEXT NOT NULL,
    display_name TEXT NOT NULL,
    base_url TEXT NOT NULL DEFAULT '',
    api_version TEXT NOT NULL DEFAULT '',
    region TEXT NOT NULL DEFAULT '',
    data_zone TEXT NOT NULL DEFAULT '',
    is_external INTEGER NOT NULL DEFAULT 0,
    is_local INTEGER NOT NULL DEFAULT 0,
    health_check_url TEXT NOT NULL DEFAULT '',
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ai_model_profiles (
    model_profile_id TEXT PRIMARY KEY,
    provider_id TEXT NOT NULL,
    model_code TEXT NOT NULL,
    deployment_name TEXT NOT NULL DEFAULT '',
    context_window_tokens INTEGER NOT NULL DEFAULT 0,
    input_price_per_1m REAL NOT NULL DEFAULT 0,
    cached_input_price_per_1m REAL NOT NULL DEFAULT 0,
    output_price_per_1m REAL NOT NULL DEFAULT 0,
    billing_currency TEXT NOT NULL DEFAULT 'USD',
    effective_from TEXT,
    effective_to TEXT,
    eu_data_zone_capable INTEGER NOT NULL DEFAULT 0,
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(provider_id, model_code),
    FOREIGN KEY(provider_id) REFERENCES ai_model_providers(provider_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS ai_model_groups (
    model_group_id TEXT PRIMARY KEY,
    group_code TEXT UNIQUE NOT NULL,
    display_name TEXT NOT NULL,
    priority INTEGER NOT NULL DEFAULT 0,
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ai_model_group_users (
    model_group_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY(model_group_id, user_id),
    FOREIGN KEY(model_group_id) REFERENCES ai_model_groups(model_group_id) ON DELETE CASCADE,
    FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS ai_task_route_policies (
    policy_id TEXT PRIMARY KEY,
    task_type TEXT NOT NULL,
    plan_code TEXT NOT NULL DEFAULT '',
    model_group_id TEXT,
    preferred_external_model_profile_id TEXT,
    preferred_local_model_profile_id TEXT,
    allow_external INTEGER NOT NULL DEFAULT 0,
    require_external_ack INTEGER NOT NULL DEFAULT 1,
    require_eu_data_zone INTEGER NOT NULL DEFAULT 1,
    fallback_local_on_error INTEGER NOT NULL DEFAULT 1,
    fallback_local_on_budget INTEGER NOT NULL DEFAULT 1,
    max_cost_eur REAL NOT NULL DEFAULT 0,
    priority INTEGER NOT NULL DEFAULT 0,
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(model_group_id) REFERENCES ai_model_groups(model_group_id) ON DELETE SET NULL,
    FOREIGN KEY(preferred_external_model_profile_id) REFERENCES ai_model_profiles(model_profile_id) ON DELETE SET NULL,
    FOREIGN KEY(preferred_local_model_profile_id) REFERENCES ai_model_profiles(model_profile_id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS ai_model_usage_ledger (
    usage_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL DEFAULT '',
    subscription_id TEXT NOT NULL DEFAULT '',
    plan_code TEXT NOT NULL DEFAULT '',
    case_id TEXT NOT NULL DEFAULT '',
    task_type TEXT NOT NULL DEFAULT '',
    model_group_id TEXT NOT NULL DEFAULT '',
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    route_type TEXT NOT NULL,
    input_tokens INTEGER NOT NULL DEFAULT 0,
    cached_input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    total_tokens INTEGER NOT NULL DEFAULT 0,
    estimated_cost_provider_currency REAL NOT NULL DEFAULT 0,
    estimated_cost_eur REAL NOT NULL DEFAULT 0,
    provider_currency TEXT NOT NULL DEFAULT 'USD',
    exchange_rate_used REAL NOT NULL DEFAULT 1,
    request_started_at TEXT NOT NULL,
    request_completed_at TEXT NOT NULL,
    latency_ms INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'ok',
    fallback_reason TEXT NOT NULL DEFAULT '',
    confidentiality_warning_ack_id TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_ai_task_route_policies_lookup
ON ai_task_route_policies(task_type, plan_code, enabled, priority);

CREATE INDEX IF NOT EXISTS idx_ai_model_usage_case_model_time
ON ai_model_usage_ledger(case_id, provider, model, request_completed_at);

CREATE INDEX IF NOT EXISTS idx_ai_model_usage_task_model_time
ON ai_model_usage_ledger(task_type, provider, model, request_completed_at);
