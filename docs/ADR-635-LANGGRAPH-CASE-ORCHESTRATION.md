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
