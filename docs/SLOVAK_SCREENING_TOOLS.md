# Slovak Screening Tools

This repository now exposes a Slovak debtor-screening helper for the public Dôvera debtor list.

## Tool

- `dovera_debtor_check`
  - purpose: search the public Dôvera debtor list by person/company name or IČO
  - output: normalized debtor records with:
    - original search query
    - fetch timestamp
    - published debtor-list snapshot date
    - debtor name
    - address
    - IČO when available
    - debt amount
    - source evidence links (`payment`, `claim`) when present
    - match type + confidence
    - source advisory text

## Screening policy

- Use the tool only with explicit user confirmation.
- Treat results as advisory evidence, not as a legal confirmation of debt status.
- If the tool returns no rows, do not claim that the subject is debt-free; the source itself says the list is informational and incomplete for legal purposes.
- Keep the search query and snapshot date in the returned screening summary so a reviewer can audit what was checked.

## Implementation

- `src/aijurisdictionagents/tools/dovera_debtors/tool.py`
- `src/aijurisdictionagents/tools/registry.py`
- `api/aijuristiction-api/app/flow_packs/default_packs.py`

## Minimal runnable example

```bash
python examples/dovera_debtor_check_demo.py
```
