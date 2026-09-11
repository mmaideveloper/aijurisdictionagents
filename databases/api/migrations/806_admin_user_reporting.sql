-- PostgreSQL reporting contract. No login or credentials are created here.
CREATE SCHEMA IF NOT EXISTS admin_reporting;
REVOKE ALL ON SCHEMA admin_reporting FROM PUBLIC;

-- Explicit exclusions, never inferred from names/email. Account removal cascades.
CREATE TABLE IF NOT EXISTS admin_reporting.excluded_users (
    user_id TEXT PRIMARY KEY REFERENCES public.users(user_id) ON DELETE CASCADE,
    reason TEXT NOT NULL CHECK (reason IN ('service', 'synthetic', 'deleted', 'restricted'))
);

CREATE OR REPLACE FUNCTION admin_reporting.check_range(p_from TIMESTAMPTZ, p_to TIMESTAMPTZ)
RETURNS VOID LANGUAGE plpgsql SET search_path = pg_catalog AS $$
BEGIN
    IF p_from IS NULL OR p_to IS NULL OR NOT isfinite(p_from) OR NOT isfinite(p_to)
       OR p_to <= p_from OR p_to - p_from > INTERVAL '366 days' THEN
        RAISE EXCEPTION 'Reporting range must be positive and at most 366 days';
    END IF;
END;
$$;

CREATE OR REPLACE FUNCTION admin_reporting.total_users()
RETURNS TABLE(total_users BIGINT)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog AS $$
    SELECT count(*) FROM public.users u
    WHERE NOT EXISTS (SELECT 1 FROM admin_reporting.excluded_users x WHERE x.user_id = u.user_id)
$$;

CREATE OR REPLACE FUNCTION admin_reporting.registrations(p_from TIMESTAMPTZ, p_to TIMESTAMPTZ)
RETURNS TABLE("time" TIMESTAMPTZ, registrations BIGINT)
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = pg_catalog AS $$
BEGIN
    PERFORM admin_reporting.check_range(p_from, p_to);
    RETURN QUERY
    WITH days AS (
        SELECT d::date AS day FROM generate_series(
            (p_from AT TIME ZONE 'Europe/Bratislava')::date::timestamp,
            ((p_to - INTERVAL '1 microsecond') AT TIME ZONE 'Europe/Bratislava')::date::timestamp,
            INTERVAL '1 day') d
    ), counts AS (
        SELECT (u.created_at::timestamptz AT TIME ZONE 'Europe/Bratislava')::date AS day, count(*) AS n
        FROM public.users u
        WHERE u.created_at::timestamptz >= p_from AND u.created_at::timestamptz < p_to
          AND NOT EXISTS (SELECT 1 FROM admin_reporting.excluded_users x WHERE x.user_id = u.user_id)
        GROUP BY 1
    )
    SELECT days.day::timestamp AT TIME ZONE 'Europe/Bratislava', coalesce(counts.n, 0)
    FROM days LEFT JOIN counts USING(day) ORDER BY days.day;
END;
$$;

CREATE OR REPLACE FUNCTION admin_reporting.latest_users(p_from TIMESTAMPTZ, p_to TIMESTAMPTZ)
RETURNS TABLE(user_id TEXT, registered_at TIMESTAMPTZ)
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = pg_catalog AS $$
BEGIN
    PERFORM admin_reporting.check_range(p_from, p_to);
    RETURN QUERY SELECT u.user_id, u.created_at::timestamptz
    FROM public.users u
    WHERE u.created_at::timestamptz >= p_from AND u.created_at::timestamptz < p_to
      AND NOT EXISTS (SELECT 1 FROM admin_reporting.excluded_users x WHERE x.user_id = u.user_id)
    ORDER BY u.created_at::timestamptz DESC, u.user_id LIMIT 10;
END;
$$;

CREATE OR REPLACE FUNCTION admin_reporting.user_tokens(
    p_from TIMESTAMPTZ, p_to TIMESTAMPTZ,
    p_offset INTEGER DEFAULT 0, p_limit INTEGER DEFAULT 100, p_sort TEXT DEFAULT 'tokens')
RETURNS TABLE(user_id TEXT, input_tokens BIGINT, cached_input_tokens BIGINT,
    output_tokens BIGINT, total_tokens BIGINT, ledger_entries BIGINT,
    estimated_entries BIGINT, unspecified_entries BIGINT, total_rows BIGINT)
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = pg_catalog AS $$
BEGIN
    PERFORM admin_reporting.check_range(p_from, p_to);
    IF p_offset IS NULL OR p_offset < 0 OR p_limit IS NULL OR p_limit NOT BETWEEN 1 AND 100
       OR p_sort IS NULL OR p_sort NOT IN ('tokens', 'user') THEN
        RAISE EXCEPTION 'Invalid reporting pagination or sort';
    END IF;
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
        WHERE l.request_completed_at::timestamptz >= p_from
          AND l.request_completed_at::timestamptz < p_to GROUP BY l.user_id
    )
    SELECT u.user_id, coalesce(a.i, 0), coalesce(a.c, 0), coalesce(a.o, 0),
        coalesce(a.t, 0), coalesce(a.n, 0), coalesce(a.e, 0), coalesce(a.unknown, 0), count(*) OVER()
    FROM public.users u LEFT JOIN usage a ON a.user_id = u.user_id
    WHERE NOT EXISTS (SELECT 1 FROM admin_reporting.excluded_users x WHERE x.user_id = u.user_id)
    ORDER BY CASE WHEN p_sort = 'tokens' THEN coalesce(a.t, 0) END DESC, u.user_id
    LIMIT p_limit OFFSET p_offset;
END;
$$;

-- Separate reconciliation categories avoid leaking deleted/excluded/orphaned identifiers.
CREATE OR REPLACE FUNCTION admin_reporting.token_reconciliation(p_from TIMESTAMPTZ, p_to TIMESTAMPTZ)
RETURNS TABLE(attribution TEXT, total_tokens BIGINT, ledger_entries BIGINT)
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = pg_catalog AS $$
BEGIN
    PERFORM admin_reporting.check_range(p_from, p_to);
    RETURN QUERY
    SELECT CASE WHEN x.user_id IS NOT NULL THEN 'excluded'
                WHEN u.user_id IS NULL THEN 'unattributed' ELSE 'eligible' END,
        sum(l.total_tokens)::bigint, count(*)
    FROM public.ai_model_usage_ledger l
    LEFT JOIN public.users u ON u.user_id = l.user_id
    LEFT JOIN admin_reporting.excluded_users x ON x.user_id = l.user_id
    WHERE l.request_completed_at::timestamptz >= p_from AND l.request_completed_at::timestamptz < p_to
    GROUP BY 1 ORDER BY 1;
END;
$$;

CREATE TABLE IF NOT EXISTS admin_reporting.coverage (
    singleton BOOLEAN PRIMARY KEY DEFAULT TRUE CHECK(singleton),
    started_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);
INSERT INTO admin_reporting.coverage(singleton) VALUES(TRUE) ON CONFLICT DO NOTHING;

CREATE TABLE IF NOT EXISTS admin_reporting.daily_activity (
    user_id TEXT NOT NULL REFERENCES public.users(user_id) ON DELETE CASCADE,
    day DATE NOT NULL,
    PRIMARY KEY(day, user_id)
);

CREATE OR REPLACE FUNCTION admin_reporting.prune_activity()
RETURNS VOID LANGUAGE sql SECURITY DEFINER SET search_path = pg_catalog AS $$
    DELETE FROM admin_reporting.daily_activity
    WHERE day < (CURRENT_TIMESTAMP AT TIME ZONE 'Europe/Bratislava')::date - 89
       OR user_id IN (SELECT user_id FROM admin_reporting.excluded_users)
$$;

CREATE OR REPLACE FUNCTION admin_reporting.capture_activity()
RETURNS TRIGGER LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $$
DECLARE event_time TIMESTAMPTZ;
BEGIN
    IF TG_TABLE_NAME = 'ai_model_usage_ledger' THEN
        IF NEW.question_id = '' THEN RETURN NEW; END IF;
        event_time := NEW.request_started_at::timestamptz;
    ELSE
        event_time := NEW.created_at::timestamptz;
    END IF;
    IF event_time >= (SELECT started_at FROM admin_reporting.coverage)
       AND event_time <= clock_timestamp()
       AND (event_time AT TIME ZONE 'Europe/Bratislava')::date >=
           (CURRENT_TIMESTAMP AT TIME ZONE 'Europe/Bratislava')::date - 89
       AND EXISTS (SELECT 1 FROM public.users WHERE user_id = NEW.user_id)
       AND NOT EXISTS (SELECT 1 FROM admin_reporting.excluded_users WHERE user_id = NEW.user_id) THEN
        INSERT INTO admin_reporting.daily_activity(user_id, day)
        VALUES(NEW.user_id, (event_time AT TIME ZONE 'Europe/Bratislava')::date)
        ON CONFLICT DO NOTHING;
    END IF;
    PERFORM admin_reporting.prune_activity();
    RETURN NEW;
END;
$$;
DROP TRIGGER IF EXISTS admin_reporting_case_activity ON public.cases;
CREATE TRIGGER admin_reporting_case_activity AFTER INSERT ON public.cases
FOR EACH ROW EXECUTE FUNCTION admin_reporting.capture_activity();
DROP TRIGGER IF EXISTS admin_reporting_question_activity ON public.ai_model_usage_ledger;
CREATE TRIGGER admin_reporting_question_activity AFTER INSERT ON public.ai_model_usage_ledger
FOR EACH ROW EXECUTE FUNCTION admin_reporting.capture_activity();

CREATE OR REPLACE FUNCTION admin_reporting.activity_coverage()
RETURNS TABLE(collection_started_at TIMESTAMPTZ, complete_days_from DATE, retention_days INTEGER)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog AS $$
    SELECT started_at, greatest((started_at AT TIME ZONE 'Europe/Bratislava')::date + 1,
        (CURRENT_TIMESTAMP AT TIME ZONE 'Europe/Bratislava')::date - 89), 90
    FROM admin_reporting.coverage
$$;

CREATE OR REPLACE FUNCTION admin_reporting.daily_active(p_from TIMESTAMPTZ, p_to TIMESTAMPTZ)
RETURNS TABLE("time" TIMESTAMPTZ, active_users BIGINT)
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = pg_catalog AS $$
BEGIN
    PERFORM admin_reporting.check_range(p_from, p_to);
    RETURN QUERY
    WITH days AS (
        SELECT d::date AS day FROM generate_series(
            (p_from AT TIME ZONE 'Europe/Bratislava')::date::timestamp,
            ((p_to - INTERVAL '1 microsecond') AT TIME ZONE 'Europe/Bratislava')::date::timestamp,
            INTERVAL '1 day') d
    ), counts AS (
        SELECT a.day, count(*) AS n FROM admin_reporting.daily_activity a
        WHERE NOT EXISTS (SELECT 1 FROM admin_reporting.excluded_users x WHERE x.user_id = a.user_id)
        GROUP BY a.day
    )
    SELECT d.day::timestamp AT TIME ZONE 'Europe/Bratislava',
        CASE WHEN d.day < coverage.complete_days_from
                   OR d.day > (CURRENT_TIMESTAMP AT TIME ZONE 'Europe/Bratislava')::date
             THEN NULL ELSE coalesce(c.n, 0) END
    FROM days d LEFT JOIN counts c USING(day)
    CROSS JOIN admin_reporting.activity_coverage() coverage ORDER BY d.day;
END;
$$;

REVOKE ALL ON ALL TABLES IN SCHEMA admin_reporting FROM PUBLIC;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA admin_reporting FROM PUBLIC;
