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

## Files

- Root mirror test: `root_contract_end_to_end_test.py`
- Main end-to-end tests: `e2etests/test_contract_end_to_end.py`
- Workflow helpers: `src/aijurisdictionagents/e2e_workflows.py`

## Run locally

```bash
pytest e2etests/test_contract_end_to_end.py root_contract_end_to_end_test.py
```

## Minimal runnable example

```bash
python examples/minimal_demo.py
```
