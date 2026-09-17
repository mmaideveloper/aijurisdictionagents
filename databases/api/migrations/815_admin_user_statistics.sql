-- Restricted account statistics. No email or usage payload is copied into reporting storage.
-- Tombstones distinguish an observed deletion from an unknown/orphan ledger identity.
CREATE INDEX IF NOT EXISTS idx_usage_ledger_reporting_user ON public.ai_model_usage_ledger(user_id);
CREATE TABLE IF NOT EXISTS admin_reporting.deleted_users (
    user_id TEXT PRIMARY KEY,
    reportable BOOLEAN NOT NULL
);
REVOKE ALL ON admin_reporting.deleted_users FROM PUBLIC;

CREATE OR REPLACE FUNCTION admin_reporting.capture_user_deletion()
RETURNS TRIGGER LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $$
BEGIN
    IF EXISTS (SELECT 1 FROM public.ai_model_usage_ledger WHERE user_id = OLD.user_id) THEN
        INSERT INTO admin_reporting.deleted_users(user_id, reportable)
        VALUES (OLD.user_id, NOT EXISTS (
            SELECT 1 FROM admin_reporting.excluded_users
            WHERE user_id = OLD.user_id AND reason IN ('restricted', 'service', 'synthetic')))
        ON CONFLICT (user_id) DO UPDATE SET reportable = EXCLUDED.reportable;
    END IF;
    RETURN OLD;
END;
$$;
DROP TRIGGER IF EXISTS admin_reporting_user_deletion ON public.users;
CREATE TRIGGER admin_reporting_user_deletion BEFORE DELETE ON public.users
FOR EACH ROW EXECUTE FUNCTION admin_reporting.capture_user_deletion();

CREATE OR REPLACE FUNCTION admin_reporting.prune_deleted_users()
RETURNS VOID LANGUAGE sql SECURITY DEFINER SET search_path = pg_catalog AS $$
    DELETE FROM admin_reporting.deleted_users d
    WHERE NOT EXISTS (SELECT 1 FROM public.ai_model_usage_ledger l WHERE l.user_id = d.user_id)
$$;

CREATE OR REPLACE FUNCTION admin_reporting.prune_deleted_usage()
RETURNS TRIGGER LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $$
BEGIN
    PERFORM admin_reporting.prune_deleted_users();
    RETURN NULL;
END;
$$;
DROP TRIGGER IF EXISTS admin_reporting_usage_deletion ON public.ai_model_usage_ledger;
CREATE TRIGGER admin_reporting_usage_deletion AFTER DELETE OR UPDATE OF user_id
ON public.ai_model_usage_ledger FOR EACH STATEMENT
EXECUTE FUNCTION admin_reporting.prune_deleted_usage();
DROP TRIGGER IF EXISTS admin_reporting_usage_truncate ON public.ai_model_usage_ledger;
CREATE TRIGGER admin_reporting_usage_truncate AFTER TRUNCATE ON public.ai_model_usage_ledger
FOR EACH STATEMENT EXECUTE FUNCTION admin_reporting.prune_deleted_usage();

CREATE OR REPLACE FUNCTION admin_reporting.users_at(p_to TIMESTAMPTZ)
RETURNS TABLE(total_users BIGINT)
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = pg_catalog AS $$
BEGIN
    IF p_to IS NULL OR NOT isfinite(p_to) THEN RAISE EXCEPTION 'A finite end date is required'; END IF;
    RETURN QUERY SELECT count(*) FROM public.users u
    WHERE u.created_at::timestamptz < p_to
      AND NOT EXISTS (SELECT 1 FROM admin_reporting.excluded_users x WHERE x.user_id = u.user_id);
END;
$$;

CREATE OR REPLACE FUNCTION admin_reporting.latest_registrations(p_from TIMESTAMPTZ, p_to TIMESTAMPTZ)
RETURNS TABLE(email TEXT, registered_at TIMESTAMPTZ)
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = pg_catalog AS $$
BEGIN
    PERFORM admin_reporting.check_range(p_from, p_to);
    RETURN QUERY SELECT u.email, u.created_at::timestamptz FROM public.users u
    WHERE u.created_at::timestamptz >= p_from AND u.created_at::timestamptz < p_to
      AND NOT EXISTS (SELECT 1 FROM admin_reporting.excluded_users x WHERE x.user_id = u.user_id)
    ORDER BY u.created_at::timestamptz DESC, u.user_id LIMIT 10;
END;
$$;

CREATE OR REPLACE FUNCTION admin_reporting.top_token_users(p_from TIMESTAMPTZ, p_to TIMESTAMPTZ)
RETURNS TABLE(email TEXT, account_status TEXT, input_tokens BIGINT, cached_input_tokens BIGINT,
    output_tokens BIGINT, total_tokens BIGINT, ledger_entries BIGINT,
    estimated_entries BIGINT, unspecified_entries BIGINT)
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = pg_catalog AS $$
BEGIN
    PERFORM admin_reporting.check_range(p_from, p_to);
    RETURN QUERY
    WITH usage AS (
        SELECT l.user_id, sum(l.input_tokens)::bigint AS i,
            sum(l.cached_input_tokens)::bigint AS c, sum(l.output_tokens)::bigint AS o,
            sum(l.total_tokens)::bigint AS t, count(*) AS n,
            count(*) FILTER (WHERE l.audit_metadata_json::jsonb ->> 'token_counting' LIKE 'estimated%') AS e,
            count(*) FILTER (WHERE coalesce(l.audit_metadata_json::jsonb ->> 'token_counting', '')
                NOT LIKE 'estimated%' AND coalesce(l.audit_metadata_json::jsonb ->> 'token_counting', '')
                <> 'provider_reported') AS unknown
        FROM public.ai_model_usage_ledger l
        WHERE l.request_completed_at::timestamptz >= p_from AND l.request_completed_at::timestamptz < p_to
        GROUP BY l.user_id
    )
    SELECT CASE WHEN u.user_id IS NULL OR x.reason = 'deleted' THEN 'Deleted user (deleted)' ELSE u.email END,
        CASE WHEN u.user_id IS NULL OR x.reason = 'deleted' THEN 'deleted' ELSE 'active' END,
        a.i, a.c, a.o, a.t, a.n, a.e, a.unknown
    FROM usage a
    LEFT JOIN public.users u ON u.user_id = a.user_id
    LEFT JOIN admin_reporting.excluded_users x ON x.user_id = a.user_id
    LEFT JOIN admin_reporting.deleted_users d ON d.user_id = a.user_id
    WHERE (u.user_id IS NOT NULL AND (x.reason IS NULL OR x.reason = 'deleted'))
       OR (u.user_id IS NULL AND d.reportable)
    ORDER BY a.t DESC, a.user_id LIMIT 10;
END;
$$;

CREATE OR REPLACE FUNCTION admin_reporting.token_reconciliation(p_from TIMESTAMPTZ, p_to TIMESTAMPTZ)
RETURNS TABLE(attribution TEXT, total_tokens BIGINT, ledger_entries BIGINT)
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = pg_catalog AS $$
BEGIN
    PERFORM admin_reporting.check_range(p_from, p_to);
    RETURN QUERY
    SELECT CASE WHEN x.reason = 'deleted' OR (u.user_id IS NULL AND d.reportable) THEN 'deleted'
                WHEN x.user_id IS NOT NULL OR (u.user_id IS NULL AND d.reportable = FALSE) THEN 'excluded'
                WHEN u.user_id IS NULL THEN 'unattributed' ELSE 'eligible' END,
        sum(l.total_tokens)::bigint, count(*)
    FROM public.ai_model_usage_ledger l
    LEFT JOIN public.users u ON u.user_id = l.user_id
    LEFT JOIN admin_reporting.excluded_users x ON x.user_id = l.user_id
    LEFT JOIN admin_reporting.deleted_users d ON d.user_id = l.user_id
    WHERE l.request_completed_at::timestamptz >= p_from AND l.request_completed_at::timestamptz < p_to
    GROUP BY 1 ORDER BY 1;
END;
$$;

REVOKE ALL ON ALL FUNCTIONS IN SCHEMA admin_reporting FROM PUBLIC;
