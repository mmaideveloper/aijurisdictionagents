# LangGraph decision explanations (#861)

The existing protected debug response/export adds `decision_evidence`, a bounded
projection of recorded decision codes. LangGraph node occurrences receive the
same explanation only when the durable event ID and owning workflow-run ID both
match. Repeated nodes stay separate; no timestamp inference or replacement with
today's topology is introduced. Existing pinned topology remains authoritative.

Explanation provenance is `recorded_decision_code` with the recorded actor.
An actor tagged model is not proof of a provider-supported reasoning summary.
Only registered deterministic reason codes are displayed in this projection;
unrecognized codes are unavailable. No free-text summaries, prompts, outputs,
checkpoints, scratchpads or hidden reasoning are copied into the new projection.
The model-supplied summary is explicitly unavailable until an actual supported
summary and reviewed minimization policy exist. No extra model call is made.

Known graph-run evidence identifies LangGraph execution. Empty historical graph
evidence yields unknown, never not-applicable. Provider/model and validator node
joins still require recorded causal identifiers from #856–#858; correlation alone
must not associate every session model call with every node. Those joins and
combined real acceptance remain outstanding for full #861 completion.

This uses the existing admin-only ledger/export, expiry and deletion controls.
No new processor, retention period, consent scope or legal-review bypass is added.
These explanations are recorded decisions, not proof of internal model reasoning
or legal correctness. This preserves data minimization and human oversight.

Run `python examples/decision_evidence_demo.py`; retain the general
`python examples/minimal_demo.py` example. Tests:
`python -m pytest api/aijuristiction-api/tests/test_decision_evidence.py`.
API lint/types and the full API suite remain mandatory.

Real E2E: use the #856 fixture with local PostgreSQL, API, frontend, MCP and the
approved Azure model; open the same actual LangGraph run through search, node
details and export; compare event IDs and topology digest. Repeat a node through
revision/resume, verify distinct occurrences and unavailable provider summary.
Also exercise an uninstrumented historical trace and injected narrative/secret
fixtures in preliminary unit tests. Save a sanitized final-state screenshot and
manifest under ignored `runs/`, delete synthetic records and retain evidence no
longer than seven days. The combined scenario is pending, not a passed E2E claim.

## Exact task execution links (#861)

New primary-router and dedicated-workflow node executions allocate an occurrence
ID before invoking model, tool or validation work. Context-local propagation carries
only run/node/occurrence identifiers into the existing diagnostic ledger. The
same occurrence ID is persisted with the graph traversal event. Admin projection
joins all three identifiers; it never guesses a join from timestamps or stage names.
The node details show the recorded provider/model or validator/version and request
ID. Missing historical, expired or paged-out evidence stays explicitly unavailable.
A node without a model call is not claimed to have performed one.

This metadata-only change adds no evaluator, model call, processor or consent
purpose. Existing admin access, seven-day retention, case deletion, provider
consent and human oversight apply. No prompts, answers or hidden reasoning are
added to these fields. This is an engineering privacy review, not a legal
compliance certification. Actual quality assessors remain deferred by the owner;
missing assessments continue to produce an incomplete/null score.

Run `python examples/node_execution_audit_demo.py` offline. Focused regression:
`python -m pytest tests/test_primary_router.py tests/test_case_workflow.py
 tests/test_correlation.py api/aijuristiction-api/tests/test_decision_evidence.py`.
The real #206 browser suites assert classifier/model joins and distinct resumed
input-validation joins; preserve the screenshot and sanitized manifest under the
seven-day E2E evidence policy.
