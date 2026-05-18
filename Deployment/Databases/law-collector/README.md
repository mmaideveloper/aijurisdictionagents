# Law collector DB backup and copy scripts

This folder contains scripts to back up a local up-to-date PostgreSQL laws database and copy it to another PostgreSQL environment (including Azure Database for PostgreSQL).

## Scripts

- `backup_and_validate_laws_db.ps1`
  - Creates a PostgreSQL custom-format backup (`pg_dump`).
  - Validates data quality for the requested country and year range:
    - at least one law exists for every year from 1995 to current year
    - every law version has an embedding vector
    - every law version has matching metadata
  - Writes a JSON validation report beside the backup.

- `copy_to_azure_postgres.ps1`
  - Exports source DB with `pg_dump`.
  - Imports to target PostgreSQL using `pg_restore --clean --if-exists`.
  - Runs sanity checks (`law_documents`, `law_versions`, `law_metadata` counts).

## Requirements

- PowerShell 7+
- PostgreSQL client tools available in PATH: `pg_dump`, `pg_restore`, `psql`
- Network connectivity to source and target PostgreSQL instances
- For Azure targets, use SSL-enabled connection strings (for example with `sslmode=require`)

## Example usage

```powershell
# Backup + validation (defaults LAWS_DB_CLOUD, years 1995..current, country SK)
./Deployment/Databases/law-collector/backup_and_validate_laws_db.ps1

# Backup + validation with explicit connection
./Deployment/Databases/law-collector/backup_and_validate_laws_db.ps1 `
  -ConnectionString "postgresql://user:pass@127.0.0.1:5432/laws_sk"

# Copy to Azure PostgreSQL
./Deployment/Databases/law-collector/copy_to_azure_postgres.ps1 `
  -SourceConnectionString "postgresql://user:pass@127.0.0.1:5432/laws_sk" `
  -TargetConnectionString "postgresql://jurisadmin:pass@server.postgres.database.azure.com:5432/laws_sk?sslmode=require"
```

## GDPR + EU AI Act guardrails applied

- Scripts process only database-level legal corpus records and produce aggregate validation output (no additional personal-data enrichment).
- Validation report stores only counts and year-level coverage gaps (data-minimization).
- Backups should be retained and deleted per your environment retention policy.
- Keep execution logs for traceability and human oversight before promoting restored data to production.
