# ADR 0660: Governed model-turn boundary

Status: accepted for implementation; real local E2E release validation pending.
Issue: [#660](https://github.com/mmaideveloper/aijurisdictionagents/issues/660).

## Problem and options

The API and agents assemble policy and evidence incrementally. Provider adapters
previously accepted plain strings and lists, with per-item clipping but no aggregate
turn budget or omission report. Keeping that arrangement is simple but cannot bound
history or inspect governance consistently. Moving assembly into each provider would
duplicate policy and create different trust boundaries. Replacing the entire chat
orchestration would broaden this change and risk existing clients.

## Decision

Introduce immutable, versioned Pydantic contracts in `llm/turn_contracts.py` and a
single deterministic builder in `llm/turn_context.py`. Preserve the existing
`LLMClient.complete(agent_name, system_prompt, conversation, documents)` interface.
`build_provider_messages` is the compatibility adapter: it snapshots legacy input
into `AgentTurnContext` and renders the same provider-neutral message structure used
by Azure Foundry, OpenAI and Ollama. New first-party runtime integrations may construct
the typed context directly and use each real adapter's `complete_turn` method. No
tool execution loop or new client endpoint is added.

The context keeps request, instructions, selected first-party skills, tools, memory,
artifact evidence, governance, provenance and budget separate. Version 1 artifact,
tool-call/result, approval, citation and stream-event schemas are available to future
integrations. Existing REST/SSE responses remain unchanged; these contracts do not
replace deployed client schemas or claim clients already consume new events.

## Security and governance boundary

Only server-created instructions and selected server-owned skill instructions enter
the system message. Historical roles, documents, memory and tool descriptions use
JSON user-role envelopes. A provenance label is not a signature or permission: never
accept a serialized internal context from an untrusted client. Skill selection and
instruction construction stay behind server authorization and first-party registries.

Artifacts require identity, provenance, sensitivity, ownership scope and retention.
Legacy inputs have no verified persistent owner/expiry: they default to confidential,
internal, turn-only artifacts. No consent, ownership or retention period is inferred
from document identifiers. The adapter records `upstream_authorized` external processing
because the existing API/router is responsible for provider authorization. A new typed
context defaults to external processing blocked. `prepare_turn` itself performs no
external call, and rejects restricted processing. Typed Azure Foundry/OpenAI calls and
non-loopback Ollama calls reject external processing unless marked upstream authorized.
The upstream caller must still enforce valid/revoked consent, artifact access and expiry
before constructing the context. Contracts do not grant tool or disclosure rights.

All consequential outputs require human review in context governance. Approval and
tool-result models describe state, never execute actions. Explicit artifact expiry
and approval expiry must be timezone-aware; persistent expiry/deletion enforcement
remains with existing storage policies and the work in #389. Public artifact/event
schemas contain only allowlisted metadata; they exclude hidden prompts, reasoning,
private owner references, artifact bodies and tool arguments. Before constructing a
public projection, the API must authorize the owner and source metadata. The only
text-bearing public event is `text_delta`, which accepts a bounded visible answer
chunk; it must never contain internal context or reasoning. Tool input schemas are
bounded JSON object schemas, not executable code or authorization instructions.

Operational model logs contain counts, not raw requests/responses, even when optional
I/O logging is enabled. Context auditing logs schema version, aggregate size and omitted
categories only. Existing protected admin debug bundles remain subject to their access,
redaction and retention controls; they are not operational logs or public contracts.
This ADR does not close #389's consent ledger, DSAR or executable retention blockers.

## Budget and failure policy

Defaults: 128,000 encoded characters, 128,000 conservative token units, 4,096 reserved
output tokens, 24,000 characters per history/memory/tool item, 8,000 per artifact.
These are deterministic application bounds, not discovered provider context limits.
The token estimator counts UTF-8 bytes plus role/message framing, conservatively
bounding ordinary byte-tokenized model input. Provider-specific limits and provider
tokenizers remain an upstream routing responsibility; no exact token count is claimed.

Policy and the current request are never clipped. If they cannot fit, raise the
content-free `context_budget_exceeded` exception. Reserve space for a category-only
truncation disclosure. Fill remaining space in this fixed order: newest history first,
artifacts in supplied order, memory in supplied order, tool descriptions in supplied
order. Render retained history chronologically. Clip values before JSON serialization,
using binary search against the actual encoded envelope cost. Empty envelopes that
cannot fit are omitted. Thus quotes, backslashes, Unicode and framing count towards
the turn budget and JSON is always complete.

`BudgetReport` records sizes and item category/index/original/retained counts, with no
text, source IDs or owner IDs. The model receives `context_truncated` with omitted
categories and policy directs it to disclose incomplete context. The corresponding
public event contract is available, but emitting new SSE events is deferred to an
explicit client integration; version 1 preserves current wire behavior.

## Rollout and rollback

Deploy through the existing shared builder. Preserve configured real providers; never
substitute mock because configuration or a budget check failed. Start with synthetic
contract and API regression tests, then validate the implemented local frontend/API
and relevant services against migrated, synthetically seeded local PostgreSQL and
the default real model before release. Keep failed/pending real E2E visible.

Rollback is a revert of this change at the compatibility boundary. There are no DB
migrations, persisted context rows, new environment variables or infrastructure inputs.
Reverting restores the previous builder and does not require data migration. Preserve
the counts-only logging policy during rollback whenever possible.

## Verification

Run `python examples/governed_turn_context_demo.py` for an offline synthetic example.
Run `python examples/minimal_demo.py` for the established repository demo.
`tests/test_turn_context.py` covers category separation, schema round trips, ownership
and expiry validation, budgeting, error behavior and public/operational privacy.
`tests/test_prompt_boundary.py` exercises Azure Foundry, OpenAI and Ollama using
deterministic provider transports. These are integration checks, not real-model E2E.
