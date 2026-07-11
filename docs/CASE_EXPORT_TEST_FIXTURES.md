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

## Model Testing Fixture Database

Tracked golden fixtures live under `tests/modelsTesting/`.

- `tests/modelsTesting/index.json` is the machine-readable registry for model-comparison runners.
- `tests/modelsTesting/cases/*.zip` stores immutable zipped case exports.
- `tests/test_models_testing_fixtures.py` validates that every registered ZIP exists, matches its SHA-256, contains the required comparison files, and carries legal-document assertions.

Use this folder for correct question/answer/document examples that should remain stable across model upgrades. Model runners should compare the live answer and generated document against the fixture's `must_contain`, `must_not_contain`, and similarity thresholds before accepting a model as safe for the scenario.

This fixture database supports the broader frontend/browser test solution in GitHub issue `#422` for account, billing, invoice, and admin E2E coverage. Keep `#422` as the main browser test initiative and use `tests/modelsTesting` as the reusable legal-answer/document fixture layer for scenarios that need model-output comparison.

Regression issue `#518` keeps the Slovak private loan-confirmation prompt deterministic: a first-turn request such as "Chcem pozicat peniaze na 1 rok..." must route to a legal-document draft with a `CASE_UPDATE_JSON.case.documents[*].content` body, so generated-document storage and PDF export do not depend on local model wording.

## Compliance Notes

- Export only the minimum fixture set required for validation.
- Prefer dedicated test accounts and synthetic legal-document data.
- Store the admin reason with enough detail to explain why the export was created.
- Keep generated fixture retention aligned with the test retention policy.
- Mark committed fixtures as synthetic or dedicated-test-account data in `tests/modelsTesting/index.json`.
- Legal-document fixtures must include human-review expectations and checks for document structure, parties, operative statement, and signature blocks.
