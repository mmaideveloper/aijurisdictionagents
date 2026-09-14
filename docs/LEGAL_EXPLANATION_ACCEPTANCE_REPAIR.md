# Acceptance repair for general explanations

Explicit general-information requests without uploaded/case documents use a dedicated
source-bound response mode. Mixed drafting/assessment requests and document workflows
retain their existing prompt, confirmation and metadata behavior. The mode uses the
existing provider/model and one completion; it does not add a model call or change routing.

Only retrieved legal text enters this mode's document context. Personal profile and
intake/drafting instructions are excluded. Missing evidence is disclosed, synthetic
sources remain explicitly illustrative, and unsupported legal conditions must remain
unresolved. This is prompt-level control, not a guarantee of legal correctness; human
review and same-model acceptance remain required.

The model-visible retrieval summary uses public law identifiers/titles without internal
document IDs. Full IDs remain in source citations, stored records and audit metadata.

Verification: API lint/types, full API tests, and the existing real local #810 scenario
with the exact production GPT-5-mini route. The regression suite checks mode selection,
evidence isolation and missing-source disclosure. Run `python examples/legal_explanation_demo.py`
for the normalization example and `python examples/minimal_demo.py` for the system demo.
The final E2E must retain a screenshot and sanitized source/model manifest under ignored
runs/ with seven-day maximum retention. A passing result must supersede the previously
recorded failed comparison; never delete or relabel a failed run as successful.

No new data collection, production configuration or schema migration. Privacy improvement:
general explanation prompts no longer receive signed-in profile defaults. Sources remain
untrusted, model identity/citations remain auditable, and human legal oversight remains.

## Acceptance result

The repaired real-model scenario passed on 2026-09-14, run
`issue-810-legal-explanation-20260914T104251Z-256f7ee0`, using the server-verified
`azurefoundryeu / gpt-5-mini` profile with no fallback. The real local frontend, API,
MCP and migrated PostgreSQL databases were used. API history retained the original
question and full answer, direct MCP and answer citations matched the synthetic seed,
and the model audit confirmed the required route. Browser checks found five headings,
one table, matching source links and stable reloaded history, without intake or internal
IDs. Visual/text review confirmed that missing procedural details were left unresolved
instead of being supplied as facts. Evidence and the final screenshot are under the
ignored run directory in the acceptance worktree.

The earlier failed runs remain failed evidence. This test validates the bounded
synthetic scenario and presentation; it does not certify current Slovak legal advice
or guarantee every future model output. Existing human oversight remains necessary.
