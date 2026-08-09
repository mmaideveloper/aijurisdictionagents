# Model Testing Case Fixtures

This folder is the tracked golden-case database for comparing model answers and generated legal documents.

It supports the broader frontend/browser test solution tracked in GitHub issue [#422](https://github.com/mmaideveloper/aijurisdictionagents/issues/422). Issue `#422` remains the main end-to-end test initiative for account, billing, invoice, and admin flows; this folder provides reusable zipped legal-answer/document fixtures that those tests and future model-comparison runners can consume.

Each case is stored as a ZIP under `cases/` and registered in `index.json`. The ZIP should contain a self-contained case export with:

- the original prompt,
- expected assistant answer,
- expected generated legal-document text,
- rendered document artifact, usually PDF,
- screenshot or HTML evidence when available,
- machine-readable assertions for model-comparison runners.

## Compliance Rules

- Use synthetic or dedicated test-account data only.
- Do not commit production customer data, secrets, API keys, access tokens, payment data, or unrelated case history.
- Keep fixture prompts and documents limited to what is needed to validate model behavior.
- Legal-document fixtures must assert human review before signing, filing, or reliance.
- If a fixture includes personal-looking values, mark them as synthetic in `index.json`.

## Adding a case

Provide the native ZIP and source issue to the repository-local skill:

```text
Use prepare-golden-test for issue #602 with the attached exported ZIP.
```

The skill copies the unchanged input to ignored
`runs/model-validation/issue-<number>/<run-id>/`, validates it, and only then promotes it to
`tests/modelsTesting/cases/` and updates `index.json`. Quarantine holds transient reports and
PDF/text/first-page evidence; it is not a second golden database and must be deleted after
review/merge or within seven days.

Every new entry starts as `technical_reviewed` after automated safety, checksum, schema, document,
PDF, source-fact, assertion, citation/warning, and persisted model-audit checks pass. A human must
then review the genuine production case/export path and explicitly approve the baseline. The same
PR receives a small promotion commit to `native_reviewed` and reruns validation. A manually
assembled ZIP may remain a development seed or `technical_reviewed`, but it cannot become
`native_reviewed` because it does not prove the production conversation, document, PDF, checksum,
and model-audit path.

Run:

```powershell
.\conda\python.exe -m pytest tests\test_models_testing_fixtures.py
```

The skill opens the dedicated PR and moves the issue to `In review`, but never merges. A later
human-approved close-task workflow performs the merge.

The runner in `aijurisdictionagents.golden_cases` supports both the native export from issue #471
(`manifest.json`, `messages.jsonl`, `ai-model-audit.json`, documents and warnings) and the older
scenario-01 seed format. New fixtures must use the native format.

Future model runners should use `index.json` as the stable entry point and treat each reviewed ZIP
as immutable fixture input. Compare normalized text and configured assertions, never PDF bytes.

## Scenario 01: private-loan payment confirmation

The tracked `issue-513-loan-confirmation` ZIP is a synthetic legacy seed. It is useful for offline
runner tests, but it is not yet evidence of a full production replay. Replace it with a native export
created through JurisDigta using the process below before marking scenario 01 legally approved:

1. Create a dedicated automation account and a new case in JurisDigta.
2. Use invented names, addresses, identifiers, dates and amounts. Do not adapt a customer case.
3. Ask for a receipt/payment confirmation for a private loan and answer follow-up questions with the
   same stable synthetic facts.
4. A human reviewer verifies the document type, parties, amount, handover/payment date, signatures,
   repayment wording, legal citations and the AI/human-review disclosure.
5. Export the case using the paid case-export endpoint/UI and verify that the ZIP contains the native
   export manifest, transcript, model audit, warnings and generated PDF. Confirm
   `manifest.json.models_used` and `ai-model-audit.json.entries` identify the actual provider, model,
   route type and status used for the case. Do not enter these values manually.
6. Use `prepare-golden-test` to create the initial `technical_reviewed` PR. Promote the same PR to
   `native_reviewed` only after explicit human approval and a successful validation rerun.

The export contains personal-looking synthetic data and model audit metadata, so retain only the
minimum fixture, never credentials or payment details. Failed/live outputs belong under ignored
`runs/model-validation/` and should be deleted according to the test-data retention policy.
