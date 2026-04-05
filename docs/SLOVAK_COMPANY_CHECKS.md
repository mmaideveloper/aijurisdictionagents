# Slovak company verification checks (Obchodný register-first flow)

This repository now includes prompt + executable tooling for Slovak legal intake so the model can:

1. Detect when a user asks for a contract with a company.
2. Check whether a relevant verification tool is available.
3. Ask for explicit user consent before running the check.
4. Return the found company data.
5. Ask for data updates if invalid/mismatched values are found.

## Current check policy

- Primary registry check: `obchodny_register_company_check` (Slovak business register verification).

Implementation modules:

- `src/aijurisdictionagents/tools/registry.py` (tool registry and dispatch)
- `src/aijurisdictionagents/tools/obchodnyregister/tool.py` (ORSR integration)
- `src/aijurisdictionagents/agents/tooling.py` (prompt rendering from registered tools)
- `src/aijurisdictionagents/agents/slovakia.py` (Slovak lawyer policy using registry-defined tools)

## Why this pattern

- Keeps the model behavior deterministic and auditable via system prompt rules.
- Uses a real tool folder layout: `src/aijurisdictionagents/tools/<toolname>/`.
- Supports your requested workflow: intake first, then optional external verification, then contract drafting.

## Minimal runnable example

Run:

```bash
python examples/slovak_company_check_minimal_demo.py
```

The example prints the generated Slovak lawyer prompt snippet including available verification checks and required user-consent behavior.
