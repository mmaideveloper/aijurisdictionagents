# General legal explanations (#810)

Current acceptance status: **failed quality comparison on the production model**.
The earlier GPT-4o-mini run below is historical evidence, not final acceptance.
See [production-model comparison](LEGAL_EXPLANATION_PROD_MODEL_COMPARISON.md).

General questions should receive a useful conditional explanation before optional
clarification. Intake about parties, identity, dates and documents is reserved for
case-specific work. Document generation still requires its existing confirmation.

The generic lawyer prompt addresses each activity separately, states jurisdiction
and assumptions, cites supplied sources and discloses missing current-law evidence.
The Slovak intake checklist is explicitly scoped to intake. Local compact prompts
follow the same answer-first policy; model routing and output budgets are unchanged.

API response normalization preserves the entire visible answer. A question mark
may belong to a heading, quotation or explanation and must never delimit the answer.
The one-question policy applies to the prompt and `case.open_questions` metadata;
it is not a destructive text filter. Existing USER-FACING envelopes are removed
from display, while the compatible CASE_UPDATE_JSON persistence path remains.

The MCP keyword gate now recognizes additional everyday legal situations, including
conviction, sentence execution, electronic monitoring, divorce and dismissal.
Retrieval expands bracelet terminology to monitoring/probation concepts. This remains
a bounded lexical policy, not universal legal-intent recognition: additional topics
need positive/negative regression cases. Fitness bracelets and ordinary electronics
must not activate retrieval solely because they contain an electronic-device term.

The web client renders ordinary and typed text answers through `AssistantMarkdown`
with react-markdown and remark-gfm. Headings, paragraphs, lists, emphasis, tables and
explicit web/source links are supported. Raw HTML is skipped, images and inputs are
disabled, and URLs are restricted to HTTP(S), local root paths and fragment links.
No model-authored images load automatically. Existing structured renderers and
generated-document previews remain separate. Technical payload documents are filtered
by kind from the normal case document view, including cached case records; stored
records, authorization and case retention/deletion are unchanged.

## Verification

Run `python examples/minimal_demo.py` for the existing system demo. A focused,
offline normalization example is `python examples/legal_explanation_demo.py`.
It uses illustrative text rather than legal advice or a provider call.

Run API lint/types with `scripts/validate_api.ps1`, API tests with
`conda/python.exe -m pytest api/aijuristiction-api/tests`, and web tests/build from
`frontend/aijurisdictionfronend` using `npm test` and `npm run build`.

Final acceptance requires the real local frontend/API/MCP/PostgreSQL/model chain,
synthetic sources and case, an audited provider route, and a final screenshot per
`E2E_TEST_EVIDENCE_RULE.md`. Store sanitized evidence under ignored `runs/` or
`artifacts/`, retain for at most seven days unless that rule requires earlier removal,
and remove task records after validation. Unit and browser mocks are not real E2E
acceptance. No production deployment is included in this change.

### Local validation on 2026-09-14

API lint/types and the full API and core test suites passed (existing skips remain).
The web suite passed 163 tests; web lint has no errors and nine existing warnings.
The production web build passed with the existing large-bundle warning. Both demos ran.

Real local acceptance used frontend 5190, API 8190, MCP 8191 and isolated PostgreSQL
55410 with migrated `issue810_api` and `issue810_laws` databases. The exact user
question reached API history unchanged. Direct MCP search/text checks found seed
`issue-810-legal-explanation`; the real answer cited the same source. Browser checks
confirmed four topic headings, an ordered list, two visible matching source links,
no internal labels, and stable content after reload and case reselection. The final
screenshot was visually reviewed. Evidence is in ignored
`runs/e2e/issue-810-legal-explanation/issue-810-legal-explanation-20260914T054538Z-986bec73/`.

The approved real provider route was `azure_foundry / gpt-4o-mini`. This verifies the
synthetic retrieval and presentation scenario, not current Slovak legal accuracy or
parity with the screenshot's GPT-5-mini. Human legal review and a comparison using
that exact model remain separate acceptance work before claiming answer parity.

Privacy review: the change avoids unnecessary personal intake and automatic remote
image loads, retains source/audit metadata and existing document confirmation and
human oversight. E2E data is synthetic, isolated and must be removed within
seven days; login material is removed immediately after the run. No new production
data collection, retention policy, environment variable or infrastructure is required.
