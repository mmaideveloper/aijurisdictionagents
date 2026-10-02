# Provision citations and full-law delivery

Ordinary-language Slovak legal questions are eligible for MCP retrieval even without
a statute number. Short follow-ups include the preceding user question. Search
results select provisions; disjoint sections are fetched individually so an unrelated
intervening section cannot consume the entire context budget. Truncated provisions
are excluded. Structured provision anchors take precedence over plain-text headings.

The model receives opaque source tokens alongside the retrieved text. The API binds
only those tokens to readable law/provision labels and persists the used sources plus
answer offsets in `presentation.citation_bindings`. Model-written references do not
establish provenance. Missing associations are visibly unverified. Retrieval is evidence
of the cited text, not a guarantee that the model's interpretation is legally correct;
human review remains required. Source text is untrusted data, never an instruction.

When a model returns a Markdown table, citation binding preserves its header and
separator syntax. Unsupported row warnings stay inside the final cell, so the UI
renders the comparison and its evidence warnings without flattening it into prose.

The answer keeps individual provision references. The Citácie sidebar deduplicates
laws by source and effective date. A law link opens `/sources/{caseId}/{citationId}`
in a new tab. That page calls
`GET /v1/cases/{case_id}/citations/{citation_id}/full-law?user_id=...`
with the API key and authenticated device headers. The endpoint checks the enabled
user, case ownership, and persisted citation, fetches the complete cited effective
version through MCP, and returns escaped plain text through the frontend. It fails
closed on missing sources, version mismatch, pagination errors, or excessive size.
No internal MCP URL or credential is returned. SK, EN and DE error states are available.

Provision metadata retains an HTTPS Slov-Lex source URL for provenance checks; internal
hosts, userinfo, query credentials, unsafe schemes and unexpected ports are rejected. Browser law links
still use the authenticated full-law route. Latest-law discovery summaries retain
metadata citations for every listed law, even when the bounded full-text context covers
only a subset. They do not acquire unsupported provision bindings from that subset.

Citation metadata uses existing case retention/deletion and authorization. The feature
adds no new external-search consent or processing purpose. Logs from source delivery
contain exception classes only; full law bodies are not duplicated in citation records.
These boundaries support GDPR data minimization and EU AI Act transparency/oversight.

## Minimal verification

```powershell
.\conda\python.exe examples/provision_citations_demo.py
.\conda\python.exe examples/minimal_demo.py
.\conda\python.exe -m pytest api/aijuristiction-api/tests/test_provision_citations.py api/aijuristiction-api/tests/test_cited_law_delivery.py
.\scripts\validate_api.ps1
```

## Real local acceptance

Use an isolated local PostgreSQL instance on port 55446 with databases `issue746_api`
and `issue746_laws`, applying current migrations. Store its data under
`runs/storage/issue746/postgres/data`. Import the approved encrypted real Azure Foundry
credential using `scripts/import_e2e_model_credentials_from_server.ps1` for this loopback
database and required model `gpt-5-mini`; never substitute a mock for acceptance.

Save the public Slov-Lex print snapshot of Act 190/2003, effective 2025-07-01, as
`runs/e2e/issue746/law.html`. `scripts/prepare_issue_746_e2e.py` seeds the public snapshot
with deterministic test identifiers and synthetic accounts, and creates a unique run ID.
Run `scripts/run_issue_746_e2e_services.py`, then
`scripts/authenticate_issue_746_e2e.py`. These use API 8246, MCP 8247 and the isolated DBs.
In the frontend directory run:

```powershell
$env:VITE_API_BASE_URL='http://127.0.0.1:8246'
$env:VITE_API_KEY='aijuris'
npx playwright test e2e/issue-746-real-citations.spec.ts --output=../../runs/e2e/issue746/playwright
```

The real browser creates a synthetic case, asks
`Ake skupiny zbrani definuje zakon, strucne popis?`, verifies Act 190/2003 and categories
A–D against §§4–7, checks persisted associations and actual model routing, opens the
full law in a new tab, and reloads the conversation. The category-to-provision assertion
accepts bullets or table rows and requires each category and its expected provision
to occur on the same answer line. The service runner first checks
the same source through direct MCP. Screenshots and sanitized result manifests stay
under ignored `runs/e2e/issue746`; private authentication material is not evidence and
must be deleted immediately after acceptance. Delete synthetic cases, local service
storage and retained evidence within seven days per `docs/E2E_TEST_EVIDENCE_RULE.md`.

The local acceptance spec skips when its private bootstrap is absent, so ordinary
CI browser regressions cannot accidentally call a real model or claim real acceptance.
