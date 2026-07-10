# Model Testing Case Fixtures

This folder is the tracked golden-case database for comparing model answers and generated legal documents.

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

## Adding A Case

1. Create or obtain a sanitized ZIP export for one scenario.
2. Add the ZIP under `tests/modelsTesting/cases/`.
3. Add one entry to `tests/modelsTesting/index.json`.
4. Include expected answer/document assertions, similarity thresholds, and legal-document checks.
5. Run:

```powershell
.\conda\python.exe -m pytest tests\test_models_testing_fixtures.py
```

Future model runners should use `index.json` as the stable entry point and treat each ZIP as immutable fixture input.
