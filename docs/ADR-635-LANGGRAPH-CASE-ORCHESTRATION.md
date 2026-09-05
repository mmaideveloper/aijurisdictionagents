# ADR 635: Registered LangGraph case workflows

Status: accepted for controlled rollout.

JurisDigta will use LangGraph for durable guided case execution while retaining the legacy
orchestrator as a rollout fallback. Case types remain the routing catalog, flow packs remain the
declarative legal configuration, and a persisted assignment connects both to a reviewed Python
graph version.

This avoids executable workflow code in the admin UI, keeps legal configuration independently
versioned, makes interrupt/resume durable, and supports deterministic enforcement around consent,
privacy, provenance, and human oversight. The cost is an additional checkpoint and audit store,
plus explicit migration/operations work. Arbitrary autonomous provider agents and unrestricted
personal-data discovery are rejected.

Published flow versions and running-case pins are immutable. Missing or incompatible
configuration uses an explicit non-automated human-review flow. Production activation remains
allowlisted and reversible with `AI_CASE_ORCHESTRATION_MODE=legacy`.

Loop termination is part of the durable workflow contract. All iterative nodes must use persisted,
bounded input, quality, and technical counters; repeated-category plus unchanged-output no-progress
detection; cancellation and deadline checks; and the graph recursion limit as a final backstop.
Terminal paths persist a stable reason code and one sanitized `workflow_terminated` event. Privacy,
consent, provenance, and mandatory legal-risk failures bypass autonomous revision and require a
blocked or human-review outcome. Reflection added later must reuse this contract rather than
introduce an independent retry counter.

Issue 753 implements that contract as an explicit
`draft -> validate -> critique -> revise -> validate` route. Critiques use stable failure categories
and policy-owned revision instructions; prompts, hidden reasoning, and case text are not copied into
the audit ledger. `quality_revision_count` is the authoritative bounded counter, while the persisted
`retry_count` and `max_revision_attempts` fields provide compatibility-facing names for the same
quality-revision budget. Privacy, consent, missing-provenance, and mandatory legal-risk failures
still bypass the loop and enter human oversight immediately.

Production and local application runtimes must use durable checkpoints. PostgreSQL remains the
shared multi-replica checkpointer; local SQLite uses a dedicated checkpoint file under
`runs/storage/api/sqlite/`. `InMemorySaver` is supported only by isolated deterministic tests and
examples that make no restart guarantee. The application projection records the durable checkpoint
marker, reconciles from the checkpoint when it detects an interrupted projection write, and exposes
a recoverable operational conflict when the checkpoint is missing. A per-checkpoint resume claim
and optional client idempotency key prevent duplicate lifecycle execution.
