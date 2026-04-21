# AIAddressValidatorAgent

`AIAddressValidatorAgent` maps Slovak address text into a structured payload suitable for `registeradries.sk` lookups.

## What it does

- detects address-like text from a user message
- extracts and normalizes core fields:
  - `kraj`
  - `okres`
  - `city`
  - `street`
  - `house_number`
  - `postal_code`
- prepares a ready-to-open `registeradries.sk` lookup URL

## Consent and memory behavior

For Slovak chat flows, when address data is relevant, the assistant should:

1. ask once whether the user wants address validation via `registeradries.sk`
2. remember the answer (`yes` / `no`) for the rest of the case
3. reuse that preference without repeatedly asking

## Minimal runnable example

```bash
python examples/address_validation_minimal_demo.py
```
