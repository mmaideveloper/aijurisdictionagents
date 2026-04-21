# AIPropertyValidatorAgent

`AIPropertyValidatorAgent` prepares Slovak **list vlastníctva (LV)** lookup and download plans.

## What it does

- accepts either:
  - `person_name` (owner lookup), or
  - `lv_number` (direct LV lookup)
- returns a structured plan with:
  - search scope (`all_cadastral_units_slovakia` for person-name-only queries)
  - provider priority (`cica.vugk.sk` and `kataster.skgeodesy.sk/eskn-portal`)
  - practical instructions for opening matched LV and downloading informative PDF/HTML output

## Search policy

- If only `person_name` is provided, the plan explicitly uses **all cadastral units in Slovakia** first.
- If `lv_number` is provided, the plan prioritizes direct LV lookup and optionally narrows by `cadastral_unit` / `municipality`.

## Person screening integration

The Slovak person/company screening flow now includes tool option:

- `slovakia_property_lv_lookup`

This allows screening workflows to include property ownership verification paths alongside company checks and web screening.

## Minimal runnable example

```bash
python examples/property_validation_minimal_demo.py
```


## Consent and memory behavior

For Slovak chat flows, when property/LV context is detected, the assistant should:

1. ask once whether the user wants LV lookup via `slovakia_property_lv_lookup`
2. remember that answer (`yes` / `no`) for the rest of the case
3. automatically reuse prior consent instead of re-asking
