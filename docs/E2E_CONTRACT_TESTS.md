# End-to-End Contract Test Scenarios

This repository now includes deterministic end-to-end simulations for two document-heavy legal workflows.

## Included scenarios

1. **Contract summary from 3 uploaded PDF pages**
   - Creates a case with the instruction `Look to contract and prepare summary`.
   - Uploads three simulated one-page PDF contract files.
   - Produces a short contract summary, recommendation, and final weighted accuracy score.

2. **Slovak lease modernization / prenajom review**
   - Creates a dummy legacy `najomna zmluva` from year 2000.
   - Reviews it against the repository's simulated current prenajom compliance checklist.
   - Produces an updated lease text plus a PDF-like diff artifact showing old vs. new clauses.

3. **Synthetic payment process**
   - Creates a synthetic user through the live API.
   - Selects the Case plan and receives a sandbox checkout URL.
   - Confirms the simulated payment and verifies that the subscription becomes `paid`.
   - Verifies guard rails: disabled plans stay unavailable, and unknown payment IDs do not activate subscriptions.

4. `api/aijuristiction-api/e2e-playwright/tests/free-plan-api-connectivity.spec.ts`
   - Creates a synthetic free-plan chat user.
   - Verifies the effective route is `free_local` through `local_ollama`.
   - Sends a legal chat prompt through `/v1/chat/sessions/{session_id}/reply` and fails if the API returns a network/model connection error.
   - Asks `Daj mi posledny zakon v systeme?` and fails if the free-plan answer reports MCP unavailability or exposes raw MCP JSON/tool fields instead of a readable Slovak answer.

5. `api/aijuristiction-api/e2e-playwright/tests/free-plan-ollama-document-pdf.spec.ts`
   - Creates a synthetic free-plan user and case.
   - Verifies the effective route is `free_local` through `local_ollama` with `qwen3:1.7b`.

The laptop-to-production local-routing smoke uses the existing connectivity spec with a synthetic
arithmetic question and a timeout longer than the configured 600-second local-model deadline:

```powershell
$env:API_BASE_URL = "https://api.jurisdigta.eu"
$env:EXPECTED_LOCAL_MODEL = "qwen3:4b"
$env:FREE_PLAN_API_E2E_TIMEOUT_MS = "660000"
npm --prefix api/aijuristiction-api/e2e-playwright run test:prod-local-routing
```

The test verifies the effective provider is `local_ollama`, optionally checks the exact configured
model, sends no customer/case data, and rejects network/internal-error text in the assistant reply.
   - Runs a Slovak request for `Splnomocnenie` for operation of a company vehicle for `ESolutions SK s.r.o.` and asks for Slovak and English generated PDFs.
   - The Slovak vehicle-authorization direct-reply path handles the exact request before local model fallback so the assistant reply cannot be empty when the user already supplied the drafting facts.
   - Fails when the assistant conversation is unprofessional, repeats the same question, or exported PDFs contain assistant/system commentary instead of only legal-document content.

6. `api/aijuristiction-api/e2e-playwright/tests/frontend-admin-local-model-selection.spec.ts`
   - Seeds browser sessions for both admin and regular users.
   - Verifies that admins see the assistant model selector with `Local Ollama - qwen3:1.7b` and `Local Ollama - qwen3:4b`.
   - Selects `Local Ollama - qwen3:4b` in the assistant workspace and sends a document-drafting prompt.
   - Verifies that regular users stay on the default `Local Ollama - qwen3:1.7b` route without a selector.
   - Fails if the frontend does not forward `model_profile_id=local_ollama_qwen4b` together with the signed-in `user_id` and `user_email` to the chat session and stream requests.

7. `frontend/aijurisdictionfronend/e2e/guest-document-share.spec.ts`
   - Opens a generated-document viewer as a synthetic authenticated sender and requests a share for exactly one PDF.
   - Captures the generated `/shared-documents/{opaque_token}` URL and opens it in a fresh browser context with no registered-user session.
   - Requests and submits a synthetic six-digit email verification code, then verifies that the frontend loads the PDF with the short-lived bearer session.
   - Confirms that the guest remains outside `/auth`, receives no case access, and still sees the qualified-human-review warning.
   - Uses synthetic identities, tokens, and PDF bytes only; the test does not log real recipients, OTPs, legal content, or share secrets.

8. `frontend/aijurisdictionfronend/e2e/golden-case-602-document-preview.spec.ts`
   - Sends the exact synthetic Slovak question from issue #602 with the disclosed Ollama Cloud `gpt-oss:20b` profile.
   - Verifies that numbered sections separated by Markdown rules remain in one complete document preview.
   - Verifies Slovak preview labels, removal of internal agent/Markdown text, the formatted HTML document viewer, and the Slovak document-share request.
   - Optionally renders the production document-share email sample and captures review-safe screenshots from synthetic data.

## Files

- Root mirror test: `root_contract_end_to_end_test.py`
- Main end-to-end tests: `e2etests/test_contract_end_to_end.py`
- Workflow helpers: `src/aijurisdictionagents/e2e_workflows.py`
- Payment-process Playwright spec: `api/aijuristiction-api/e2e-playwright/tests/payment-process.spec.ts`

## Run locally

```bash
pytest e2etests/test_contract_end_to_end.py root_contract_end_to_end_test.py
```

Run the Playwright payment-process simulation:

```bash
cd api/aijuristiction-api/e2e-playwright
npm run test:payment
```

Run the live free-plan Ollama document/PDF simulation:

```bash
cd api/aijuristiction-api/e2e-playwright
npm run test:free-plan-document
```

Run the frontend admin-selected local model scenario:

```bash
cd api/aijuristiction-api/e2e-playwright
npm run test:frontend-admin-local-model
```

Run the unregistered guest document-share frontend scenario:

```bash
cd frontend/aijurisdictionfronend
npm run test:e2e:guest-document-share
```

Run golden case #602 and optionally create screenshot evidence:

```powershell
.\conda\python.exe examples\golden_case_602_email_preview.py output\playwright\issue-602-email-preview.html
$env:GOLDEN_602_EMAIL_PREVIEW = (Resolve-Path output\playwright\issue-602-email-preview.html).Path
$env:GOLDEN_602_EVIDENCE_DIR = (Resolve-Path docs\images).Path
Set-Location frontend\aijurisdictionfronend
npm run test:e2e -- golden-case-602-document-preview.spec.ts
```

Run the opt-in issue #612 live browser regression against the production EU Azure Foundry
project while keeping the API, frontend, database, files, and synthetic user local:

```powershell
.\scripts\run_issue_612_azure_foundry_e2e.ps1
```

The runner configures `azureFoundryEU / gpt-5-mini` at the project endpoint ending in
`/api/projects/documentprocessing`, then verifies that the streamed reply succeeds through the
OpenAI-compatible `/openai/v1` client without a legacy `api-version` query parameter. It refuses
mock fallback and fails when the production credential is unavailable. When a static Foundry key
or token is not configured, the runner authenticates only as the repository service principal and
uses a short-lived Cognitive Services token; it never uses the currently signed-in Azure user.
Evidence is written under
`runs/e2e/issue-612-azure-foundry-v1/<UTC timestamp>/`: a sanitized JSON manifest and a final-state
screenshot. The isolated SQLite database and files are kept under
`runs/storage/issue-612-azure-foundry-e2e/<UTC timestamp>/`. Both paths are Git-ignored and must be
removed within seven days. The request uses a generated identity and a fixed connectivity marker;
no customer, legal-case, password, token, or credential content is retained. The response remains
an AI draft requiring human review and is not used for an automated legal decision.

The live-provider check must retain the configured provider gate. Missing Ollama Cloud or
Azure Foundry credentials must not be replaced with `mock`; deterministic route fixtures are
used only for browser/UI regression coverage.

The payment-process E2E is GDPR/privacy-by-design safe for local and scheduled runs: it uses generated identities, local test storage, log-only email transport in CI, and the API sandbox checkout contract instead of a real payment-provider charge.

## Minimal runnable example

```bash
python examples/minimal_demo.py
```
