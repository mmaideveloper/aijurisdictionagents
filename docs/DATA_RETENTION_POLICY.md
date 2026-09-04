# Data retention and deletion policy

Status: implemented baseline for issue #389. Privacy/legal owner approval is required before production release.

JurisDigta applies storage limitation by data class rather than one universal period. Legal holds and
binding statutory duties suspend deletion only for the affected records; the reason, owner, and review
date must be documented outside user-authored content.

| Data class | Default retention | Enforcement |
|---|---:|---|
| Registration, device, OAuth, and MFA challenges | Until `expires_at` | Deleted by `python -m app.retention_job_main` |
| Revocable document-share links and codes | Until `expires_at` | Share and access-audit rows deleted by the retention job |
| Soft-deleted case messages, uploads, generated files, extracted text, vectors, and citations | 30 days after case deletion | Database content and local artifacts hard-deleted by the retention job |
| Active case content | While the case/account is active or a documented legal basis requires it | User/operator deletion workflow; plan write windows do not silently erase active legal files |
| AI model usage audit | 365 days | Privacy-minimized rows deleted by the retention job |
| Consent and Data Subject Access Request (DSAR) evidence | While required to prove compliance or resolve a claim | Privacy-preserving audit proof of the request and outcome; exported personal data and direct content are never stored in compliance events |
| Hash-chained compliance events | Six years unless legal/privacy owner approves a shorter period | Append-only during the evidence period; no raw prompts, documents, secrets, or direct identifiers |
| Application logs and telemetry | 7 days by the configured Loki/monitoring policy | Infrastructure retention; labels must remain aggregate and redacted |
| Database/backups | 7 days for the declared Azure PostgreSQL server; other environments require an approved recovery window | `infra/bicep/main.bicep` configures `backupRetentionDays: 7`; DSAR erasure propagates when a backup is restored |
| Accounting records | Generally ten years after the relevant accounting year | Segregated statutory retention; never erased by the application case-content job |

## Execution

The API worker entry point is:

```powershell
.\conda\python.exe -m app.retention_job_main
```

The protected operator endpoint `POST /v1/compliance/retention/run` requires `confirmed=true`.
Each run writes a sanitized manifest to `retention_runs` and a pseudonymous compliance event. The job
never silently switches databases and uses the configured API database/storage backends.

Remote blob deletion and backup pruning remain fail-closed infrastructure responsibilities: a remote
object is not reported as deleted unless its storage adapter actually confirms deletion. A restored
backup must be kept isolated, have current migrations applied, and rerun DSAR/retention tombstones
before serving traffic.

## Data-subject workflows

- Access/export: `GET /v1/compliance/users/{user_id}/dsar/export` returns machine-readable JSON,
  messages/communications, subscriptions, citations, consent history, and a file manifest with size and
  SHA-256 rather than embedding binary documents.
- Restrict: `PUT /v1/compliance/users/{user_id}/processing-restriction` blocks model and external-tool
  execution before routing while preserving the data for review.
- Delete/anonymize: `POST /v1/compliance/users/{user_id}/dsar/actions` requires explicit confirmation,
  erases case content and local artifacts, disables credentials/subscriptions, and leaves a
  pseudonymous account/case tombstone for referential and compliance evidence.

## Verification and evidence

Use synthetic users and content only. Run `pytest tests/test_compliance.py
api/aijuristiction-api/tests/test_compliance_api.py`. Final production E2E acceptance additionally
requires local PostgreSQL, real services/model routing, a sanitized manifest, and a stable screenshot
under the ignored `runs/` or `artifacts/` paths per `docs/E2E_TEST_EVIDENCE_RULE.md`.
