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
- `src/aijurisdictionagents/tools/obchodnyregister/tool.py` (ORSR integration via official `https://sluzby.orsr.sk/api/legal-person` search endpoint plus `https://sluzby.orsr.sk/api/legal-person/extract-full` detail endpoint)
- `src/aijurisdictionagents/tools/company_checks.py` (question recognition + tool execution for company seat checks)
- `src/aijurisdictionagents/agents/tooling.py` (prompt rendering from registered tools)
- `src/aijurisdictionagents/agents/slovakia.py` (Slovak lawyer policy using registry-defined tools)

## ORSR lookup behavior

- The ORSR tool now queries the official JSON endpoint `/api/legal-person` instead of scraping the legacy HTML search page.
- Parsed company data is taken from the live `filteredCount` / `data` payload shape returned by ORSR.
- The top ranked match is enriched through `/api/legal-person/extract-full`, so the tool can also return current stakeholders, statutory representatives, company-signing text, deposit data, and equity value.
- Returned matches are ranked so an exact business-name or IČO match is preferred over fuzzy partial matches. This is important for names such as `ESolutions SK s.r.o.`, where generic substring search can otherwise surface unrelated companies first.
- Company status is now normalized as `Aktívna` by default and switches to `v likvidácii` when the current ORSR detail indicates liquidation, for example in the current company name or current liquidator data.

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

It also demonstrates recognition + execution for this style of user question:

`Zisti mi ci spolocnost Esolution SK s.r.o. sidli v Poprade?`
