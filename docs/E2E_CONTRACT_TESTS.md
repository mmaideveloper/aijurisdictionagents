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

The payment-process E2E is GDPR/privacy-by-design safe for local and scheduled runs: it uses generated identities, local test storage, log-only email transport in CI, and the API sandbox checkout contract instead of a real payment-provider charge.

## Minimal runnable example

```bash
python examples/minimal_demo.py
```
