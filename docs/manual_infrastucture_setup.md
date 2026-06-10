# Manual Infrastructure Setup

This document tracks infrastructure setup that cannot be completed only by repository code, CI, or local scripts.

## Rule

Whenever a task adds or changes manual infrastructure requirements, update this file in the same change. Include:

- Provider or portal name.
- Required account or owner.
- Test and production environment steps.
- Secrets, environment variables, certificates, keys, callback URLs, domains, or app identifiers.
- Validation steps after setup.
- Rollback or deletion steps.
- GDPR and EU AI Act notes when personal data, legal-risk outputs, or user transparency are involved.

Do not commit real secrets, private keys, certificates, Firebase config files containing sensitive project data, or Apple credentials.

## Azure PostgreSQL Laws Collector Migration

Related runbook: `docs/AZURE_POSTGRES_MIGRATION.md`

Purpose: migrate the existing local PostgreSQL laws collector database into Azure PostgreSQL Flexible Server and run the laws collector as an Azure Container Apps Job that resumes from completed archive/monthly ZIP state, probes one sequential Slovak law per run, and exits when no new law exists.

### Provider And Owner

- Provider: Microsoft Azure.
- Required owner: repository Azure service principal from `.env`; do not use a personally signed-in Azure CLI account for repository Azure work.
- Target environments: `test` first, then `prod` after backup restore and job validation.

### Manual Setup Steps

1. Authenticate with `.\infra\scripts\login_service_principal.ps1 -EnvFilePath .env`.
2. Confirm Azure subscription, resource group, PostgreSQL Flexible Server, Container Apps environment, ACR, storage account, managed identity, and Application Insights names for the target environment.
3. Back up the local `laws_sk` PostgreSQL database with `pg_dump --format custom` into an ignored operator path such as `runs/storage/laws-collector/backups/`.
4. Create or select the Azure PostgreSQL Flexible Server and database named by `AZURE_LAWS_POSTGRES_DATABASE_NAME_SK`.
5. Enable required database extensions, including `vector`, before restoring embeddings.
6. Restore the dump with `pg_restore --no-owner --no-privileges` using `sslmode=require`.
7. Apply current laws collector schema migrations with `scripts/databases/apply_laws_db_schema.py`.
8. Validate restored row counts, `collector_import_state`, and `collector_progress`.
9. Deploy `laws-collector` with `LAWS_COLLECTOR_IMPORT=zip`, live fixture, one worker cycle, `AZURE_LAWS_COLLECTOR_MAX_PROBES=1`, `LAWS_COLLECTOR_MAX_RUNNING_TIME=60`, and single job parallelism/completion.
10. Start one manual Azure Container Apps Job execution and inspect logs for skipped completed ZIP state and either one imported sequential law or `No new laws for SK`.
11. Remove temporary operator firewall rules after validation.
12. Repeat for production only after the test migration and manual job execution are verified.

### Secrets And Environment Values

- `AZURE_CLIENT_ID`
- `AZURE_CLIENT_SECRET`
- `AZURE_TENANT_ID`
- `AZURE_SUBSCRIPTION_ID`
- `AZURE_RESOURCE_GROUP`
- `AZURE_LOCATION`
- `AZURE_POSTGRES_SERVER_NAME`
- `AZURE_LAWS_POSTGRES_DATABASE_NAME_SK`
- `AZURE_POSTGRES_ADMIN_USERNAME`
- `AZURE_POSTGRES_ADMIN_PASSWORD`
- `AZURE_CONTAINERAPPS_ENVIRONMENT`
- `AZURE_CONTAINER_REGISTRY`
- `AZURE_MANAGED_IDENTITY_NAME`
- `AZURE_STORAGE_ACCOUNT_NAME`
- `AZURE_LAWS_STORAGE_CONTAINER_NAME`

### Validation Steps

- `pg_restore --list <dump>` succeeds before restore.
- Azure `law_documents` count matches the source database.
- `collector_import_state` shows completed archive/monthly state expected for the migrated database.
- `collector_progress` contains the latest imported law and next probe cursor.
- A manual Azure job run completes successfully and does not replay completed archive ZIP work.
- Logs contain `No new laws for SK` when the live tail is current.

### Rollback Notes

- Delete the scheduled Container Apps Job or redeploy it as a manual job to stop scheduled executions.
- Restore the local dump into a replacement Azure database or restore from Azure PostgreSQL backup.
- Point the job back to the previous validated database connection string if available.
- Delete temporary firewall rules and revoke any temporary credentials after rollback.
- Keep the local dump until at least one scheduled Azure job run has completed and the restored database has been validated.

### Privacy And Compliance Notes

- Treat database dumps and connection strings as sensitive operational data.
- Do not commit dumps, passwords, or full connection strings.
- Use least-privilege Azure identities and remove temporary operator network access after migration.
- Preserve collector state tables for traceability and human oversight of legal data ingestion.
- Avoid logging personal data or legal-risk user outputs during migration and validation.

## Firebase Cloud Messaging For Document-Ready Mobile Push

Related task: https://github.com/mmaideveloper/aijurisdictionagents/issues/343

Purpose: send privacy-safe Android and iOS push notifications when a user's document package is ready.

### Provider Decision

Use Firebase Cloud Messaging directly.

- Android receives push notifications through FCM.
- iOS receives push notifications through APNs configured in Firebase/FCM.
- Do not use Azure Notification Hubs for this task unless a later task explicitly changes the provider decision.

### Manual Setup Steps

1. Create or select the Firebase project for JurisDigta.
2. Enable Firebase Cloud Messaging.
3. Register the Android app using the production Android package name.
4. Download the Android Firebase configuration file required by Flutter/Android setup.
5. Register the iOS app using the production iOS bundle identifier.
6. Download the iOS Firebase configuration file required by Flutter/iOS setup.
7. In Apple Developer, create or identify the APNs key/certificate for JurisDigta push notifications.
8. Upload the APNs key/certificate details to Firebase for the iOS app.
9. Create a Firebase service account or workload identity configuration for the backend sender.
10. Store backend Firebase credentials in GitHub Environments and Azure runtime secrets for `test` and `prod`.
11. Add documented example entries to `.env.example` for any new local configuration variables.
12. Update `docs/GITHUB_ENVIRONMENTS.md` with the exact required GitHub Environment secrets and variables for `test` and `prod`.
13. Configure mobile deep links/universal links for opening the ready document view from a notification.
14. Verify Android push delivery on a physical or emulator device with Google Play services.
15. Verify iOS push delivery on a physical iOS device.
16. Verify notification tap opens the authenticated document view or a safe loading/error state.

### Privacy And Compliance Notes

- Require explicit user opt-in before registering a device token for document-ready notifications.
- Provide localized consent and notification text per supported country/language.
- Delete or deactivate device tokens on opt-out, logout where applicable, and account deletion.
- Push payloads must not contain document text, legal facts, case names, party names, email addresses, or other personal data beyond the minimum routing data.
- Notification text should stay generic, for example: `Documents are ready` and `Open JurisDigta to review them`.
- Document URLs or deep links must be authenticated or short-lived/signed and must not expose document contents or sensitive metadata.
- Logs must redact device tokens and avoid document contents or legal facts.

### Rollback Notes

- Disable the backend push sender configuration if push delivery causes operational issues.
- Keep document generation and in-app document-ready status functional even when push sending is disabled.
- Revoke compromised Firebase service account credentials immediately and rotate the corresponding GitHub/Azure secrets.
