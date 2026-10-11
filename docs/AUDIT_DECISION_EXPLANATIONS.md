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
