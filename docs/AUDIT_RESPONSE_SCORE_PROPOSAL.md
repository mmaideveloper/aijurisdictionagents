# Final response assessment proposal (#860)

Status: draft for product/quality-owner review. No aggregate is enabled by this
change. Existing routing confidence is not a final response quality score.

Proposed policy ID: `response-quality`, version `1-draft`. The proposal uses
deterministic weighted arithmetic over separately produced assessments, on a
0–100 scale. It is not a probability of legal correctness and cannot authorize
delivery of legally consequential advice without the existing human safeguards.

| Dimension | Proposed weight | Required evidence |
| --- | ---: | --- |
| Source grounding | 40% | Claim-to-source assessment with source versions |
| Factual consistency | 30% | Assessed contradictions/unsupported claims |
| Request coverage | 20% | Assessed requested requirements |
| Presentation clarity | 10% | Versioned readability/structure assessment |

Proposed review threshold: 85, inclusive. Below it requires human review; above
it does not waive any existing review requirement. Weights and threshold are
proposals, not calibrated recommendations. The product/quality owner must approve
the rubric, assessor versions, applicability rules, threshold and evaluation set
before activation. Current source-presence and profile-cleanup checks are not
valid substitutes for these dimensions.

Gate precedence is fixed in the proposal: inactive/unapproved policy ->
`pending_policy_approval`; any critical input/output-security, privacy/consent or
grounding gate fails -> `blocked`; otherwise any missing/error/unverifiable gate,
required dimension, source version, evaluator version, exact answer revision or
evidence reference -> `incomplete`. Each of those states has `score: null`.
Only complete assessments with every mandatory gate passed may be aggregated.
No renormalization over available dimensions. Critical failure cannot be averaged
away, including when all dimension values are 100.

Arithmetic uses decimal weighted sums and rounds once to two decimals, with
half-up rounding. Persist the input components, score, method, scale, immutable
policy version/digest, evaluator identity/version, timestamp, answer revision,
source/evidence references, gate dispositions, coverage and human-review state.
NaN, infinity, negative/out-of-scale values and duplicate dimension IDs are errors.
An answer edit creates a new assessment; historical scores are never recalculated
under new weights. Model-estimated components must be labeled separately from
the deterministic aggregation. No new external evaluator is authorized here.

This metadata design reuses the protected admin ledger, seven-day diagnostic
retention and case/session deletion. Do not store prompts, raw answers, sensitive
findings, credentials or hidden reasoning in score records. Evaluation uses
synthetic cases. GDPR/EU AI Act engineering review: minimize linked identifiers,
preserve purpose and access controls, keep clear assessment limitations and human
oversight; this proposal is not a legal compliance certification.

Runnable synthetic arithmetic example:
`powershell -File examples/response_score_proposal.ps1`. This verifies candidate
arithmetic and gate handling; it does not activate production scoring. The general
repository example remains `python examples/minimal_demo.py`.

After approval and #858 evidence completion, implement persistence/API/UI and run
real E2E on local frontend/API/MCP/PostgreSQL and the approved Azure model:

1. Complete synthetic evidence reproduces the persisted score exactly.
2. Missing dimension yields null score and an incomplete UI state.
3. Failed critical gate blocks even with maximum quality components.
4. Rewrite yields a new answer/assessment; earlier score stays on old revision.
5. Policy change preserves the historical version and arithmetic.
6. Admin export matches the UI; ordinary-user access is denied; deletion removes
   assessment links. Capture sanitized screenshot/manifest under ignored `runs/`
   and remove evidence within seven days.

Approval and these E2E scenarios are pending. Do not mark #860 complete or claim
that the application now produces a calibrated final response score.
