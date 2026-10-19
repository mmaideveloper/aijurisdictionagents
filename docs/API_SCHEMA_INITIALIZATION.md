# Concurrent API schema initialization (#935)

Repeated PostgreSQL API-store initialization takes transaction advisory lock 840935
before any schema DDL. `CREATE INDEX IF NOT EXISTS` alone can deadlock when concurrent
requests upgrade locks on the users table. PostgreSQL releases the advisory lock at
transaction commit or rollback; SQLite behavior is unchanged. No user data, consent,
retention or model routing behavior changes. No new settings or secrets are needed.

The scheduled regression keeps parallel workers and runs a four-thread PostgreSQL
initialization check before API scenarios. Use only a disposable loopback database:

```powershell
python -m pytest tests/test_api_db_init_postgres.py -q
python examples/minimal_demo.py
```

The integration test skips without explicit `DB_OPTION=postgres` and loopback
`DB_CLOUD`. GitHub's ephemeral scheduled database is destroyed after the job.
