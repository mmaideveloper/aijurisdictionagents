# Production-model comparison for #810

On 2026-09-14, the full local browser -> API -> MCP -> migrated PostgreSQL flow was
rerun with the original question and the exact production profile shown in the
user's screenshot: `azurefoundryeu:gpt-5-mini`. Read-only server inspection confirmed
the enabled provider/profile, deployment `gpt-5-mini` and empty model overrides.
The approved SSH importer transferred the credential without exposing it; the
local bootstrap encrypted it and verified a live response. No production customer
records were copied or production settings changed.

The local paid synthetic-user route explicitly selects that profile. The actual
`chat_reply` audit records `azurefoundryeu / gpt-5-mini`; no fallback or mock was used.
Services: frontend 5190, API 8190, MCP 8191, PostgreSQL 55410, with migrated
`issue810_api` and `issue810_laws` and deterministic source `issue-810-legal-explanation`.

Reference: [user-supplied shared ChatGPT answer](https://chatgpt.com/share/6aa78466-4548-83eb-b8a1-47c5cbc1990d).
Its underlying model is not established by the shared page. Matching the JurisDigta
production model does not establish that ChatGPT used the same model, prompt or tools.

| Criterion | Shared ChatGPT reference | Final local GPT-5-mini run |
| --- | --- | --- |
| Direct opening | Gives a conditional overview | Gives a conditional overview with synthetic-source caveat |
| Work and shopping | Separate topic sections | Both explained under rendered topic headings |
| Readability | Headings, emphasis and table | Three headings, lists and one rendered comparison table |
| Sources | Links to public official sources | Links to the exact seeded MCP source; synthetic, not current-law validation |
| Follow-up | Offers further tailoring after the answer | Unsolicited intake/document offer remains |
| Display metadata | No internal document ID in reference | Internal synthetic document ID appears in model prose |
| Source fidelity | Not legally adjudicated in this test | Adds conditions absent from the synthetic source |
| Reload | Not tested | Same answer and citations after reload and case reselection |

## Result: failed quality acceptance

The first same-model attempt produced no Markdown headings/table and several follow-up
questions. We removed remaining intake-first conflicts and made the general-answer
format explicit. The rerun improved presentation but still fails: it offers intake and
drafting, exposes a document identifier and adds unsupported specifics (for example,
escort/third-person shopping conditions and technical restrictions absent from the seed).
These are claims unsupported by the supplied evidence; this comparison does not decide
whether each claim is legally true or false in an actual case.

The verifier intentionally fails; it was not relaxed to turn this output into a pass.
The PR remains draft and task In progress. Required remaining work is reliable
source-fidelity validation and general-explanation output validation, followed by a
fresh same-model E2E. Production answer-quality parity must also be checked against
verified current legal sources; synthetic retrieval evidence alone cannot establish it.

## Evidence and reproducibility

Final run: `issue-810-legal-explanation-20260914T055958Z-5d6dfead`.
Ignored evidence directory: `runs/e2e/issue-810-legal-explanation/<run-id>/`.
It contains input/result manifests, direct MCP proof, the synthetic answer, a final
comparison screenshot and an additional screenshot of the answer opening. Browser
checks confirmed three headings, one table, two matching citation links and stable
reloaded history. Screenshots contain only synthetic account/case information.

The earlier failed-formatting run is retained separately as failed evidence.
Retain artifacts for at most seven days; remove login/OTP material immediately and
stop task services after validation. No evidence is committed. Setup commands are in
`manual_infrastucture_setup.md`. The original runnable examples still work.

After the last prompt change, the full core suite and four credential-bootstrap
regressions passed. Script lint passed. Application API/frontend code did not change
in this follow-up; their previously recorded checks still apply. Passing unit tests
does not override the failed real-model quality acceptance.
