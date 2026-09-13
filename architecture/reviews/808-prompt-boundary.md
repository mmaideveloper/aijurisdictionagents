# Issue 808: model instruction boundaries

Source review: issue [808](https://github.com/mmaideveloper/aijurisdictionagents/issues/808),
original reviewed revision `6be7b01a0a4e9d3e2b372f0c6a783fee40143365`.
The findings establish instruction-boundary defects, not demonstrated exfiltration.

| Boundary | Change | Verification |
| --- | --- | --- |
| Client role to stored history | Public creation accepts only user; assistant/system rejected with 422 | API rejection before persistence |
| Stored role to provider | Every historical role serialized as nonprivileged JSON data | Provider payload tests and compaction regression |
| Documents, profiles, memory, MCP to policy | Explicit evidence envelopes, bounded values, preserved source identifiers | Normal/compact prompt tests, all three adapters |
| Country/language to policy | Explicit alias mapping, no prefix matching or arbitrary values | Metadata validation and correction tests |
| Attack to user-visible response | Localized direct refusal; source warning accompanies legal answer | Real browser screenshot and model evaluation |

Only the separate, server-owned `system_prompt` argument establishes privileged
instructions. Callers must never concatenate user text into that argument. Historical
roles or claimed agent names are not provenance; they cannot mint privileged messages.
This avoids inventing trusted origin for legacy data and requires no destructive migration.
Administrative policy remains the responsibility of existing authorized internal callers.

Documents have a shared 24,000-character content budget, at most 8,000 characters per
document, bounded identifiers and filenames. Conversation values are capped at 24,000
characters per message. Values are truncated before JSON encoding so delimiters remain
escaped and envelopes valid. Source records are not modified. Context compaction counts
legacy system records and summarizes them as untrusted data instead of retaining them
outside the conversation limit. Current public user input remains a request subject to
server policy; a stored assistant/system message is context, never policy.

Detection is supplementary and deliberately does not claim universal attack recognition.
It covers common SK/EN/DE extraction, override, role-marker and zero-width variants.
The provider trust boundary applies even when the detector misses an attack. Source
warnings do not delete source material, grant permission, or replace tool/consent gates.
Ordinary quoted legal instructions remain available as evidence. Model resistance is
probabilistic; evidence must record failures, including excessive refusal of benign tasks.

New security events contain a reason code, source type, correlation ID and policy
version only. Existing case access, retention, deletion/export and human review safeguards
remain required. No new processor or personal-data collection is introduced. These are
privacy-by-design controls, not a GDPR/EU AI Act compliance certification or risk classification.

Run `python examples/prompt_boundary_demo.py` for the offline boundary demonstration;
`python examples/minimal_demo.py` remains the general runnable example. API gates are
`scripts/validate_api.ps1` and `conda/python.exe -m pytest api/aijuristiction-api/tests`.
Provider tests live in `tests/test_prompt_boundary.py`. Real acceptance uses local migrated
PostgreSQL, API, MCP and frontend with approved Azure Foundry credentials and synthetic
law/account/case data. Store screenshots and sanitized manifests under ignored
`runs/e2e/issue-808-prompt-boundary/`; remove evidence and transient login state within
seven days. Delete synthetic cases and task-specific records after verification; never
delete another task's database or records. A failed real-model run is not a pass merely
because a subsequent retry passes. Fix and rerun the entire fixed corpus.

Deploy only after applicable gates pass on the exact commit. If rollback is necessary,
disable affected inference paths or ship a corrected boundary; never restore public
privileged roles. Mobile and simulator consume the same warning text and HTTP contract.

## Reproducible local acceptance

1. Use `scripts/import_e2e_model_credentials_from_server.ps1` with `-DatabaseUrl`
   targeting the isolated loopback `issue_808_e2e` database and `-VerifyModel`.
2. Start/migrate the laws database with `skills/start-postgres/scripts/start_postgres.ps1 -Project laws-collector -DatabaseName laws_issue_808_e2e`.
3. Run `conda/python.exe scripts/prepare_issue_808_e2e.py`. SQL fixtures are under
   `databases/laws-collector/seeds/issue808/`. They are synthetic, including the injected
   command; do not load them into production.
4. Run `conda/python.exe scripts/run_issue_808_e2e_services.py` (API 8188, MCP 8178).
   Start the frontend with the `start-frontend-api` launcher,
   `-ApiBaseUrl http://127.0.0.1:8188 -Port 5188`.
5. Run `node scripts/verify_issue_808_browser.mjs`. The browser signs in with the synthetic
   account through the real UI, retrieves its OTP only from the local PostgreSQL outbox,
   creates the case through the frontend, asks the grounded question, then asks to reveal
   the original system prompt and captures the warning. Transient login material must
   never appear in screenshots or result manifests.
6. Run `conda/python.exe scripts/verify_issue_808_evidence.py <browser-evidence-directory>`
   to reconcile source IDs, tool calls and the actual provider/model audit entry.
7. Run `conda/python.exe scripts/evaluate_issue_808_models.py` for corpus `808-v2`:
   nine attack families, SK/EN/DE, paired benign controls, three independent repetitions
   each (162 checks). A structured Azure `content_filter` response is an expected refusal
   only for a direct attack; every benign/indirect case must return the expected grounded
   facts. Unexpected errors fail. The first corpus run retained four such provider blocks
   as unspecified failures; v2 records them explicitly and was rerun in full. This model
   probe complements, and does not replace, the real frontend/API/MCP E2E.

The initial browser run over-refused a legitimate question when its source contained an
attack. The revised shared policy explicitly instructs the model to ignore attack sentences
and continue from valid legal facts. Preserve that failed evidence alongside the rerun.
Finite successful tests do not establish universal prompt-injection resistance.
