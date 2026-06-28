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

3. `api/aijuristiction-api/e2e-playwright/tests/free-plan-api-connectivity.spec.ts`
   - Creates a synthetic free-plan chat user.
   - Verifies the effective route is `free_local` through `local_ollama`.
   - Sends a legal chat prompt through `/v1/chat/sessions/{session_id}/reply` and fails if the API returns a network/model connection error.

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

The payment-process E2E is GDPR/privacy-by-design safe for local and scheduled runs: it uses generated identities, local test storage, log-only email transport in CI, and the API sandbox checkout contract instead of a real payment-provider charge.

## Minimal runnable example

```bash
python examples/minimal_demo.py
```
