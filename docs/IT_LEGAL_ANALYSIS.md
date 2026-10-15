# Právna analýza pre IT (SK + EU)

[#909](https://github.com/mmaideveloper/aijurisdictionagents/issues/909),
[UC-003](../architecture/use-cases/UC-003-organizational-it-legal-analysis.md).
The distinct case type `sk.it.legal_analysis` covers organizational IT, data warehouses,
analytics and AI, including non-health sectors. It shares software assessment
evidence/review controls with separate intake, trusted prompt and history.

## Web, API and simulator

Select a private case in the web assistant and expand **Právna analýza pre IT · SK +
EU**. Supply the description, country codes, sector, separate entities, purposes,
data categories, roles, grounds, flows/suppliers, hosting/transfers, access/security,
retention/deletion, internal policies and rights/transparency arrangements. AI projects
also require intended AI purposes and oversight. Describe an unavailable policy as
unavailable; do not claim it exists. No patient-level records are required. Select
only necessary minimized organizational evidence and acknowledge external processing.
The account's versioned privacy consent for external models must also permit it;
case acknowledgment does not override an account privacy restriction.

Missing fields return questions without calling an external model. Countries other
than SK/EU, or EU without a national country, stop complete assessment and explain
the limit. Use ISO codes; names are not silently mapped. Acknowledge each purpose
separately: administration, analytics, research, AI training and development/testing
are not interchangeable legal purposes. Common ownership is not sharing authorization.
Pseudonymization is not anonymization; external-processing acknowledgment is not
patient consent or a processing lawful basis.

The result shows preliminary applicability, prioritized actions/owners, original
legal provisions, conditional document recommendations with reasons/content/evidence,
verification plans and limitations. Checklist categories distinguish law, contracts,
internal policy and recommended practice. Actions start open; authorized human review
with original evidence is required for verification. Missing policies and sources
remain unverified. Document drafting/PDF export and mobile support are excluded.
Action origins are also explicit: law, contractual, internal_policy or recommended.
Policy/contract gaps require an exact uploaded excerpt rather than an unrelated law.
The IT validator rejects explicit provision numbers that do not match the cited
retrieved provisions. This checks references, not full semantic legal entailment;
source relevance and completeness still need human review. When the model omits a
structured document checklist, the server supplies conditional working-record
recommendations labelled recommended, with purpose, owner and expected contents.
These are not asserted mandatory legal documents or completed organizational controls.

Base API resource: `/v1/cases/{case_id}/it-assessments?user_id=...`.
Existing API key, authenticated device/user, case access and mutation write-window
controls apply. POST accepts `request_id`, `document_ids`, `external_acknowledged`,
optional `selected_model_profile_id`, and `facts` with description, nullable
personal_data/health_data/uses_ai and `it_context`. Context contains the intake fields
above; countries is an array of codes, remaining fields are bounded strings. Omitting
context on this endpoint asks the intake questions.

| Operation | Behavior |
|---|---|
| GET / POST base | IT-only history / idempotent create |
| GET / DELETE `/{assessment_id}` | Authorized case-private read / delete |
| PATCH `/{assessment_id}/actions/{action_id}` | Revision-bound human review |
| PATCH `/{assessment_id}/supplier-checklist/{item_index}` | Receive/review document evidence |

Read/review/delete reuse the shared case-authorized resource semantics; IDs alone
never grant access. Legacy software drafting/export also reject IT-kind assessments.
Results record case type, scope/date, graph/prompt/version/hash, source provenance
and actual provider/model. Reassessment retains history. A provider failure is visible;
an unavailable selected model may fall back only through the existing disclosed
configured real-model policy, never silently to mock.

In web chat or the simulator, start with “Právna analýza pre IT” or a data-warehouse
description. Deterministic intake asks one question at a time; it does not claim to
extract every fact from the opening paragraph. Use comma-separated country codes
and áno/nie for boolean questions. After intake confirm the explicit case-bound
external-processing phrase. Questions are not recorded as answers; “Odvolávam súhlas”
revokes acknowledgment. Subsequent corrections use the structured web form/API;
use a new case for a different initiative. Both channels call the same assessment.

## Scenarios, validation and lifecycle

Original synthetic fixture: Czech ZdravieHospital owns 20 separate hospital entities
and proposes patient/administration data pooling, analytics, AI and software variants.
Keep CZ: disclose unsupported Czech national-law coverage, never substitute Slovak
law. A separately labelled Slovak 20-entity variant exercises the full SK/EU path.

`python examples/minimal_demo.py` demonstrates deterministic intake/scope without
an external model. API regression: `conda/python.exe -m pytest
api/aijuristiction-api/tests/test_organizational_it.py`; lint/types:
`scripts/validate_api.ps1`. Synthetic model/source tests are not real E2E acceptance.
Final validation requires migrated local PostgreSQL, uniquely seeded synthetic law,
accounts and cases, direct MCP checks, a case created in the real frontend, actual
Azure Foundry route and matching visible source IDs. Follow
[E2E_TEST_EVIDENCE_RULE](E2E_TEST_EVIDENCE_RULE.md); missing prerequisites mean pending.
Retain sanitized screenshots/manifest under ignored runs/ or artifacts/ for at most
seven days; clean synthetic records/files after capture. Synthetic laws test plumbing,
not substantive legal correctness.

### Reproduce the real local acceptance run

1. Run the profile sync gate, activate the task-local conda runtime, install frontend
   dependencies, and start local PostgreSQL with the repository launcher using
   `-DatabaseName aijurisdiction_e2e_909`. Create the dedicated `laws_e2e_909` database
   in that same loopback test cluster. These databases must contain synthetic data only.
2. Use `scripts/import_e2e_model_credentials_from_server.ps1 -UseExistingPostgres
   -DatabaseUrl <branch-local-loopback-connection> -VerifyModel` to import the approved
   credential, or bootstrap existing approved E2E values with
   `python scripts/bootstrap_e2e_model_credentials.py`. Never print the env file.
3. Run `python scripts/run_issue_909_e2e.py`. It applies laws migrations, reuses the
   parameterized SQL fixture assets, seeds a uniquely named synthetic source/account
   and versioned external-model consent, and checks direct MCP retrieval. Ports:
   frontend 5199, API 8199, MCP 8299, PostgreSQL 5432. No production resource is used.
4. Sign in using the synthetic account named in ignored input-manifest.json. Create
   an `issue909 synthetic ...` case through the frontend. Test CZ without external
   processing and save cz-boundary.jpg; explicitly switch to the separate Slovak
   variant, complete intake, acknowledge processing and run the real assessment.
5. Run `python scripts/verify_issue_909_e2e.py --fallback`. It checks the persisted
   provider, graph and seeded citations, then requests a nonexistent model profile.
   Select its newest history entry in the frontend and verify the visible fallback
   disclosure and actual real route. Save a stable final-state.jpg showing citations
   and a fallback-state.jpg showing disclosure; run the verifier with `--finalize`.
6. Stop the task-owned services and remove the two dedicated test databases and
   task run files after preserving sanitized evidence. Never drop a shared or
   production database. Evidence expires within seven days. Reruns need a fresh
   credential bootstrap if the isolated API database was removed.

No new database, environment variable, provider or cloud resource is required.
Existing assessment JSON storage uses kind=organizational_it/organizational_it_chat;
case deletion removes derived data. Existing retention and external-processing/EU
routing policy apply; no new plaintext case/model logging. Public-source searches
use fixed topics, not case text. SQL assets remain under databases/ and local data
under runs/storage/. Disable the catalog case type and hide the workspace entry for
rollback; retain history for authorized read/deletion. Source freshness, completeness,
legal grounds and AI risk classification always require expert verification.
