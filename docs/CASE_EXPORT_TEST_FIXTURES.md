# Case Export Test Fixtures

Case exports create ZIP fixtures for model-validation tests. Use synthetic data when preparing golden fixtures and avoid exporting real customer personal data into test repositories.

## User Export

Paid users can export their own case from **My Profile > Opened cases**. Each active case row has an export button that downloads the ZIP from:

```text
GET /v1/cases/{case_id}/export?user_id={user_id}
```

## Admin Export

Admins can export a selected user's cases from **Admin > Case resets**. Search for a user by email, open the user's cases, enter an admin reason, then use the export button on each case row.

Admin exports are audited and call:

```text
GET /v1/admin/cases/{case_id}/export?user_id={target_user_id}&reason={admin_reason}
```

The exported ZIP is intended as the source of truth for automated model-validation runs. It includes case metadata, user/system messages, AI model audit data, citations, warnings, source documents, rendered PDFs, and checksums where available.

## Compliance Notes

- Export only the minimum fixture set required for validation.
- Prefer dedicated test accounts and synthetic legal-document data.
- Store the admin reason with enough detail to explain why the export was created.
- Keep generated fixture retention aligned with the test retention policy.
