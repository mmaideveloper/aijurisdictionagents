-- Apply separately as a DBA after the API migration. Set the password through
-- interactive psql \password, never a SQL file, CLI argument or GitHub variable.
DO $$ BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'jurisdigta_user_report') THEN
        CREATE ROLE jurisdigta_user_report LOGIN NOINHERIT NOSUPERUSER NOCREATEDB
            NOCREATEROLE NOREPLICATION NOBYPASSRLS;
    END IF;
    IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'jurisdigta_user_report'
        AND (rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR rolbypassrls))
       OR EXISTS (SELECT FROM pg_auth_members WHERE member =
                  (SELECT oid FROM pg_roles WHERE rolname = 'jurisdigta_user_report')) THEN
        RAISE EXCEPTION 'Reporting role has unexpected privileges or membership';
    END IF;
END $$;
ALTER ROLE jurisdigta_user_report SET statement_timeout = '10s';
ALTER ROLE jurisdigta_user_report SET default_transaction_read_only = on;
ALTER ROLE jurisdigta_user_report CONNECTION LIMIT 3;
GRANT USAGE ON SCHEMA admin_reporting TO jurisdigta_user_report;
GRANT EXECUTE ON FUNCTION admin_reporting.total_users(),
    admin_reporting.registrations(timestamptz, timestamptz),
    admin_reporting.latest_users(timestamptz, timestamptz),
    admin_reporting.user_tokens(timestamptz, timestamptz, integer, integer, text),
    admin_reporting.token_reconciliation(timestamptz, timestamptz),
    admin_reporting.daily_active(timestamptz, timestamptz),
    admin_reporting.activity_coverage()
TO jurisdigta_user_report;
DO $$ BEGIN
    IF EXISTS (SELECT FROM pg_class c JOIN pg_namespace n ON c.relnamespace = n.oid
               WHERE n.nspname IN ('public', 'admin_reporting') AND c.relkind IN ('r', 'v', 'm')
               AND (has_table_privilege('jurisdigta_user_report', c.oid, 'SELECT')
                 OR has_table_privilege('jurisdigta_user_report', c.oid, 'INSERT')
                 OR has_table_privilege('jurisdigta_user_report', c.oid, 'UPDATE')
                 OR has_table_privilege('jurisdigta_user_report', c.oid, 'DELETE'))) THEN
        RAISE EXCEPTION 'Reporting role must not have direct application table access (including PUBLIC grants)';
    END IF;
END $$;
