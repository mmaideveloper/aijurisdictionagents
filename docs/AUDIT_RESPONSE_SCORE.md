# Response assessment contract (#860)

The owner approved implementation of the candidate rubric with missing-evidence
gates on 2026-10-11. Policy `response-quality/1` weights grounding 40%, factual
consistency 30%, request coverage 20%, and clarity 10%; review threshold is 85/100.
This approves the aggregation contract, not the validity of an untested evaluator.
No new model call or assessor is enabled by this change.

`assess_response` accepts versioned, bounded evidence for the exact answer
revision. Missing dimensions, source versions or mandatory gates produce
`incomplete` with a null score. Failed input security, output security,
privacy/consent or grounding gates produce `blocked` with a null score. Decimal
arithmetic rounds once, half up, to two places. Duplicate dimensions/gates and
nonfinite or out-of-range values are rejected. An existing human-review
requirement is never cleared. A score is not a probability of legal correctness.

Every chat assistant message records an assessment tied to its message UUID in
the existing protected diagnostic ledger. Current chat does not run approved
dimension assessors, so these assessments accurately remain incomplete. Old
evidence is never applied to a new message UUID. Dedicated workflow assessment
integration and approved dimension assessors remain pending; missing historical
records stay missing, without reconstructing scores at read time.

The admin trace and ZIP expose `response_score_evidence`; the existing admin UI
shows each answer revision, policy version, missing evidence and review state.
Historical assessments retain their original policy digest, weights, components,
evaluator/source references and timestamp. Reads do not recalculate them.
There is no public write endpoint for assessments. No raw prompt, answer,
finding text or hidden reasoning is added. Existing admin authorization,
seven-day expiry and case/session deletion apply without extending retention.
Provider consent and human legal oversight remain unchanged.

Run `python examples/response_score_demo.py` offline. The general example remains
`python examples/minimal_demo.py`. Tests: `python -m pytest tests/test_response_score.py
api/aijuristiction-api/tests/test_response_score_evidence.py` and frontend
`npm test -- --run src/__tests__/responseScoreEvidence.test.tsx`.
Real acceptance must assert a persisted incomplete assessment and its exact
delivered message UUID in the local PostgreSQL/API/MCP/Azure browser scenario,
then verify the admin view and export, capture a sanitized screenshot and clean
up synthetic records. Complete numeric arithmetic tests are synthetic contract
tests, not evidence that live chat has comprehensive assessments.
