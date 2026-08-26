# E2E test evidence rule

Every user-facing E2E scenario must prove both the machine contract and the result visible to a user. A passing HTTP response without final UI evidence is not sufficient.

## Real local acceptance environment

Final acceptance for a user-facing E2E scenario must exercise the implemented local system rather
than a fabricated browser state. Start the real local frontend, API, MCP server, and all workers or
services used by the changed path. Use local PostgreSQL databases with the current production
migrations and deterministic synthetic records in every database involved in the scenario.

Mocks remain useful for deterministic unit, integration, and preliminary browser regression tests,
but they do not satisfy final E2E acceptance. The final run must not intercept the changed backend
path with Playwright routes, substitute mocked model or database responses, or display manually
injected UI results.

Use the configured default real model unless the task explicitly specifies another model. If a
synthetic user requests a model that does not exist or is unavailable, verify that the application
visibly discloses the problem and falls back to the configured default real model. Record the
requested model, selected provider/model, and fallback disclosure in the sanitized result manifest.
Never use `mock` as that fallback. When the task specifically requires validation of the unavailable
model, fallback behavior may be tested, but it does not satisfy the task's real-model acceptance
criterion; report that criterion as failed or pending.

Synthetic accounts, cases, documents, identities, and task-specific database records are mandatory.
Real public law or court-decision data may supplement the scenario, but production customer or
personal data must not be copied into the test databases. Tag database rows and generated files with
a unique test-run identifier, remove them after the test where practical, and apply the retention
requirements below.

### MCP and legal-retrieval scenarios

For a change involving MCP or legal retrieval, final acceptance must prove the complete chain:

1. Seed deterministic synthetic law or legal-source records in the relevant local PostgreSQL database.
2. Query the running MCP/API path and assert the expected synthetic source identifiers, content markers, and citations.
3. Create a new synthetic case through the running frontend.
4. Ask a question designed to retrieve the seeded source.
5. Assert that the visible answer contains the expected grounded result and that the frontend citation resolves to the same source returned by MCP.
6. Capture the stable final UI state without exposing credentials or personal data.

If any required service, migration, database seed, or real-model credential is unavailable, the run is
not a pass. State the missing prerequisite and leave final real E2E validation pending.

### Local real-model credential bootstrap

Real-model E2E credentials are sourced from the ignored branch-local `.env` keys
`E2E_AZURE_FOUNDRY_ENDPOINT`, `E2E_AZURE_FOUNDRY_API_VERSION`,
`E2E_AZURE_FOUNDRY_DEPLOYMENT`, and exactly one of `E2E_AZURE_FOUNDRY_API_KEY` or
`E2E_AZURE_FOUNDRY_AD_TOKEN`. They must not be committed, printed, attached to test evidence, or
passed on a command line. Prefer a dedicated least-privilege E2E credential and rotate a production
credential after any transfer outside its approved hosts.

An authorized operator can start local PostgreSQL, create and migrate the branch-specific API
database, import the currently approved `azure_foundry` / `azure_foundry_gpt_4o_mini` server
credential without displaying it, and verify a real model call with:

```powershell
.\scripts\import_e2e_model_credentials_from_server.ps1 -VerifyModel
```

The import decrypts the credential inside the production API container, transfers it only through
the authenticated SSH process, writes it to the ignored local `.env`, re-encrypts it with the local
branch key, and clears process copies after use. If the branch has no valid
`AI_MODEL_CREDENTIAL_ENCRYPTION_KEY`, the importer creates a strong random local key and preserves
it in the same ignored `.env`; it never replaces an existing valid key. The importer starts the
local PostgreSQL container, derives a separate database name from the current Git branch, applies
the current API migrations, and refuses non-loopback destination databases. The
server credential reveal remains an auditable privileged action. Do not use this import in CI.

## Required evidence

1. Capture at least one final-state screenshot after the last business outcome is visible and stable.
2. Keep a trace on failure and a concise machine-readable result manifest.
3. For generated documents, retain the PDF, verify its `%PDF-` signature, non-zero size, expected page count, and extracted expected text.
4. Render the first PDF page to PNG next to the final UI preview screenshot.
5. Use ordered names: `01-audio-transcript.png`, `02-message-submitted.png`, `03-document-preview.png`, `04-generated-document.pdf`, and `05-pdf-first-page.png`.
6. Record the actual provider/model route, local services exercised, synthetic test-run/seed identifiers, and expected versus observed source identifiers in the sanitized manifest. Do not record credentials, tokens, passwords, OTP values, connection strings, or real personal data.

For a golden document scenario, use `prepare-golden-test` after exporting the case. Its ignored
quarantine must retain the final-state screenshot when the scenario is user-facing, the generated
PDF, extracted expected text, and the first-page PNG. The validator checks PDF structure and text;
the screenshot remains visual evidence and cannot replace those checks. The tracked golden ZIP
remains the only fixture, while extracted evidence stays transient.

## Voice scenarios

- Use only an approved synthetic audio fixture; real-person recordings are prohibited.
- Record the fixture locale and expected normalized transcript.
- Verify speech-to-text before submit and prove the submitted normalized text equals the reviewed UI transcript.
- Raw audio is transient input and must not be copied into logs, traces, screenshots, reports, or databases.
- Keep voice consent explicit; never bypass the application consent control.

## Legal-document safeguards

- Use synthetic identities and addresses only.
- Preview and PDF must say the output is a draft requiring human review before signing or reliance.
- Assert document type, parties, amount, due date, and currency in extracted PDF text. Visual comparison supplements these assertions; it does not replace them.
- Fail when preview is missing, PDF download fails, facts materially differ, or human-review wording is absent.
- A legal-basis scenario must assert the same verified provision and named act in the document
  preview, extracted PDF text, and structured citations. Use an official source URL and keep the
  deterministic fixture's effective/as-of date visible in its metadata; the fixture does not
  substitute for a separate live-law freshness integration test.

## Canonical audio-to-PDF scenario

`mobile_app/e2e-playwright/cases/audio-payment-confirmation.json` represents a synthetic request for confirmation of a EUR 5,000 payment to Janko Hraško at Testovo 10, due by the end of the year.

Minimal runnable example:

```powershell
cd mobile_app/e2e-playwright
npm ci
npm run test:case-rule
```

Run the full controlled browser scenario with:

```powershell
cd mobile_app/e2e-playwright
npm ci
npm run test:audio
```

The command generates an approved synthetic WAV locally, passes it to Chromium as the fake microphone source, controls the browser Web Speech boundary, verifies that the reviewed transcript is the exact message submitted to the system, and downloads a valid PDF. The fixture may use a non-Slovak installed synthetic voice because speech recognition is controlled in this test; the manifest must record `sttBoundary: controlled-browser-web-speech` and the result must not be reported as a live Azure STT accuracy measurement.

A separate provider integration test is required to claim live Slovak Azure STT accuracy. That test must use a working Cognitive Services subscription/resource, remain opt-in, and must not replace the deterministic browser E2E gate.

## Retention

Local evidence belongs under ignored `mobile_app/e2e-playwright/artifacts/` and should be deleted after review or within seven days. CI retention must be seven days or less unless a documented audit requirement mandates longer.

## LangGraph proof

A case-workflow acceptance manifest must record the real provider/model, local services and
PostgreSQL database, synthetic run/case identifiers, pinned graph/flow versions, expected and
observed node path, MCP source IDs, artifact IDs, and audit event IDs. It must assert ordered
`langgraph_run_started`, assignment pin, interrupt, resume, input validation, MCP result, output
validation, final review, and completion/escalation events. Missing events, legacy routing, mocks,
or unavailable prerequisites fail the test. Document scenarios also retain the PDF, first-page
render, structural/text validation, and a stable final-state screenshot for at most seven days.
