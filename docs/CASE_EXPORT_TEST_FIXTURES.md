# Case Export Test Fixtures

Case exports create ZIP fixtures for model-validation tests. Use synthetic data when preparing golden fixtures and avoid exporting real customer personal data into test repositories.

## User Export

Paid users can export their own case from **My Profile > Opened cases**. Each active case row has an export button that downloads the ZIP from:

```text
GET /v1/cases/{case_id}/export?user_id={user_id}
```

## Admin Export

Administrators use **Admin > Case resets > Request consented case export**. A dedicated `case_export_permissions` grant is required in addition to the admin role. Enter the exact case IDs and purpose. Each owner approves or denies in **My Profile > Case export requests**. Requests expire after 24 hours; approved archives expire after one hour and permit one download. Changing a selected case invalidates the request. Revocation blocks remaining access. Downloaded copies cannot be recalled.

The authenticated API is `POST /v1/case-exports`, `POST /v1/case-exports/{request_id}/decision`, and `POST /v1/case-exports/{request_id}/download`. Identity comes from device authentication, not an asserted user ID. The former admin GET export endpoint returns 403. Owner statutory exports remain separate from paid convenience exports.

The exported ZIP is intended as the source of truth for automated model-validation runs. It includes case metadata, user/system messages, AI model audit data, citations, warnings, source documents, rendered PDFs, and checksums where available.

## Upload, quarantine, and promotion

Use the repository-local `prepare-golden-test` skill for every new native export. For example:

```text
Use prepare-golden-test for issue #602 with the attached exported ZIP.
```

The skill first copies the submitted ZIP unchanged to
`runs/model-validation/issue-<number>/<run-id>/`. This ignored directory is temporary quarantine,
not a second fixture database. It preserves the original while archive paths, compressed sizes,
executables, secrets/payment credentials, native schemas, internal checksums, issue facts, PDFs,
citations, warnings, and persisted model-audit fields are checked. Validation reports, extracted PDF
text, a retained PDF copy, and its first-page PNG also stay there. Delete the quarantine run after
review/merge or within seven days.

Only after every deterministic check passes may the unchanged ZIP be copied to
`tests/modelsTesting/cases/` and registered in `tests/modelsTesting/index.json`. That directory is
the only tracked golden-fixture location. Unsafe, incomplete, non-synthetic, or unrelated case
exports must fail before tracked promotion.

## Model Testing Fixture Database

Tracked golden fixtures live under `tests/modelsTesting/`.

- `tests/modelsTesting/index.json` is the machine-readable registry for model-comparison runners.
- `tests/modelsTesting/cases/*.zip` stores immutable zipped case exports.
- `tests/test_models_testing_fixtures.py` validates that every registered ZIP exists, matches its SHA-256, contains the required comparison files, and carries legal-document assertions.

Use this folder for correct question/answer/document examples that should remain stable across model upgrades. Model runners should compare the live answer and generated document against the fixture's `must_contain`, `must_not_contain`, and similarity thresholds before accepting a model as safe for the scenario.

This fixture database supports the broader frontend/browser test solution in GitHub issue `#422` for account, billing, invoice, and admin E2E coverage. Keep `#422` as the main browser test initiative and use `tests/modelsTesting` as the reusable legal-answer/document fixture layer for scenarios that need model-output comparison.

Regression issue `#518` keeps the Slovak private loan-confirmation prompt deterministic: a first-turn request such as "Chcem pozicat peniaze na 1 rok..." must route to a legal-document draft with a `CASE_UPDATE_JSON.case.documents[*].content` body, so generated-document storage and PDF export do not depend on local model wording.

## Core CI regression coverage

The `prepare-golden-test` regression suite generates its synthetic PDF with PyMuPDF, which is a
declared core dependency. Keep fixture construction within the dependencies installed by
`python -m pip install -e ".[dev]"`; the `core_build` workflow runs the complete root test suite on
Python 3.13 with that installation only. Tests for real-model E2E bootstrap safeguards
must explicitly select `azurefoundry` when the workflow-level deterministic mock setting would
otherwise mask the database safety condition under test.

`core_build` runs for changes to the root package manifest, core source, root tests, scripts,
skills, and its own workflow definition. This ensures a test or skill dependency regression is
checked on the pull request that introduces it instead of being discovered by a later `src/**`
change on `main`.

## Compliance Notes

- Export only the minimum fixture set required for validation.
- Prefer dedicated test accounts and synthetic legal-document data.
- Store the admin reason with enough detail to explain why the export was created.
- Keep generated fixture retention aligned with the test retention policy.
- Mark committed fixtures as synthetic or dedicated-test-account data in `tests/modelsTesting/index.json`.
- Legal-document fixtures must include human-review expectations and checks for document structure, parties, operative statement, and signature blocks.

The preparation delivery boundary is deliberate: the skill creates a dedicated branch/worktree,
validates and promotes a `technical_reviewed` fixture, runs tests, commits, pushes, opens a PR to
`main`, comments on the issue, and moves the task to `In review`. It never merges automatically.
After explicit human approval, the same PR receives a small `native_reviewed` promotion commit and
reruns validation; the normal human-approved close-task workflow performs any later merge.

## Consent gate (#922)
The legacy admin GET export is denied. Use the web consent request workflow backed by `/v1/case-exports`; each owner must approve and the named administrator needs dedicated export permission. See [encryption and consent](CASE_ENCRYPTION_AND_CONSENT.md). Use synthetic cases only for fixtures.
