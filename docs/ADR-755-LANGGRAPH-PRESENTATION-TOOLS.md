# ADR 755: Flow-assigned presentation tools

Status: accepted

## Context

LangGraph workflows produce valid structured results, but a model-authored HTML response would mix
data, presentation, and executable markup. That would make output inconsistent across clients and
create an avoidable injection boundary. Users also need an explicit way to request JSON or plain
text without gaining access to prompts, credentials, consent records, or unrestricted tool payloads.

## Decision

Graph v4 adds a `select_presentation` node after final case review. Each immutable flow pack assigns
a bounded `presentation_policy`: a default renderer, a reviewed renderer allowlist, permitted user
overrides, and payload limits. The active payment-confirmation reference is flow v5.

The selection order is deterministic:

1. Honor an explicit supported user format request.
2. Otherwise ask the configured model to propose one renderer from the flow-filtered public list.
3. Validate that proposal against the flow, result shape, renderer version, and client capability.
4. Use the flow default, then readable text, when any check fails.

The model receives renderer metadata and result shape only. It does not receive the result, case
facts, prompts, or tool payloads for this decision. The API returns a versioned data block; the web
client maps its renderer ID to a trusted React component. It never executes model-authored HTML.

The registered v1 renderers are `result_card`, `key_value_table`, `data_table`, `notice`,
`document_preview`, `text`, `sanitized_json`, and `action_link`. The reference flow does not assign
`action_link`. Links are accepted only from trusted application code and only for `/app/` routes.

`sanitized_json` is available to ordinary users only after an explicit request. It is a bounded,
redacted projection of user-visible results. Unrestricted raw tool responses remain limited to
authorized developer/debug facilities and are never placed in the presentation block.

## Consequences and controls

- Web, mobile, and future clients can implement the same schema without parsing prose.
- Unknown renderer or schema versions fail to the already supplied readable assistant text.
- Citations, reviewed tool names/statuses, and legal human-review notices remain visible alongside
  every rich rendering.
- Presentation selection events store only policy/version/shape/reason identifiers; they do not
  duplicate personal facts or result bodies.
- Presentation blocks follow the owning case/session retention, export, and deletion lifecycle.
- Flow changes require a new immutable version, preserving resumability of pinned older runs.

This applies GDPR data minimization and privacy by design, and supports EU AI Act transparency,
traceability, and human oversight for legal-risk output.

## Alternatives rejected

- Model-generated HTML: rejected because sanitization alone is a fragile executable-content boundary.
- One global renderer list: rejected because a tool appropriate for one legal flow may be unsafe or
  misleading in another.
- Always returning raw JSON: rejected because it degrades accessibility and can expose unnecessary
  internal fields.

## Rollback

Switch orchestration to the existing `legacy` mode for new conversations. Existing graph/flow
versions remain immutable and pinned. Clients must continue to display `fallback_text` when a typed
presentation block is absent or unsupported.
