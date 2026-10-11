# Recorded validation evidence (#858)

The protected debug lookup/export includes `validation_evidence`: retained check
observations and explicit coverage for input structure/security, output
quality/security, grounding and hallucination assessment. Missing evidence never
means passed, unsupported or not-run. Runtime observations distinguish passed,
failed, blocked, error, not-run and unsupported. No numeric score is synthesized.

Currently instrumented producers:

| Producer | Scope | Outcome/action |
| --- | --- | --- |
| required_facts v1 | Required facts present | Continue or collect input |
| workflow.review_output | Injected output reviewer | Continue or human review |
| workflow.review_safety_and_gdpr | Injected consent/source-presence reviewer | Continue or block |
| chat.profile_section_cleanup v1 | Narrow missing-profile section cleanup | Continue or rewrite |

Injected reviewer implementation versions remain unknown; the recorded core
instrumentation revision does not claim to identify the injected validator.
Source presence is not source entailment, comprehensive privacy review or a
hallucination assessment. These categories remain missing until actual assessors
are connected and evaluated. No new validator or threshold is enabled here.

Each attempt has an execution UUID and recorded parent operation, bounded reason
code, decision and latency. New workflow drafts receive opaque artifact IDs in
checkpoint state; output and safety checks reference that draft. Draft revisions
receive new IDs, so prior evidence must not be applied to a rewritten answer.
Legacy drafts, input facts and ordinary chat currently lack a persisted artifact
reference and explicitly report missing linkage. Completing those associations,
validator version registration and real-provider acceptance remain #858 work.

No new raw prompts, output text, sensitive findings, content hashes or hidden
reasoning are copied into these audit fields. Exceptions retain their error state
without their message. Existing admin authorization, seven-day expiry and owning
case/session deletion apply. The code does not change gate behavior, provider
consent or human oversight. This engineering design is not a compliance certification.

Run `python examples/validation_audit_demo.py`; the general example remains
`python examples/minimal_demo.py`. Focused verification:
`python -m pytest tests/test_validation_audit.py tests/test_case_workflow.py api/aijuristiction-api/tests/test_validation_evidence.py`.

Real E2E scenarios to run on the combined #206 changes with local migrated
PostgreSQL, frontend, API, MCP and the approved real Azure model:

1. Synthetic ordinary chat: cleanup observation appears, missing grounding and
   hallucination checks remain missing, citation IDs match seeded source records.
2. Dedicated workflow: missing facts trigger collection; populated facts pass;
   output placeholder failure retains human-review action; absent consent blocks.
3. Revise the synthetic draft: artifact ID changes and old checks do not attach
   to the new answer. Repeat/resume retains distinct check execution IDs.
4. Protected admin view/export returns identical check IDs; ordinary users are
   denied; delete the synthetic case and verify its retained records are removed.
5. Capture final UI screenshot and sanitized expected/observed manifest. Keep
   evidence under ignored `runs/` for at most seven days; never retain private auth.

These scenarios are a test specification, not a claim of executed acceptance.
