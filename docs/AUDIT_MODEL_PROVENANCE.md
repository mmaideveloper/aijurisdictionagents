# Model-selection provenance (#857)

Model routing emits a metadata-only `model_router/route_selected` observation,
including rejected routes. Each configured adapter captures the selected policy
at construction and includes that snapshot in its actual completion-start event.
Later policy edits cannot change the historical snapshot. The policy digest is a
SHA-256 of the allowlisted policy fields, not a hash of personal prompts.

The snapshot records task, selected/requested profile, route type, stable reason
code, core revision, policy fields/digest, provider, alias and deployment name.
Unknown narrative reasons become `selection_reason_unavailable`. Provider URLs,
credentials, arbitrary administrative reasons and case contents are excluded.
Provider API version, model alias, deployment and provider-reported model revision
are distinct. A reported model name does not prove an immutable revision.
Missing provider revision remains `unavailable`; it is never guessed from a name.

Existing decision envelopes retain flow/version/task references. Join observations
using the recorded request/parent and correlation IDs, not timestamp adjacency.
Prompt-template metadata is explicitly `not_recorded` until a versioned template
identifier is available at the call site. No rendered prompt hash is introduced.
This is metadata in the existing protected diagnostic ledger, not a separate
content store or external telemetry processor. Existing enabled-admin access,
seven-day expiry and case/session deletion controls apply. The change does not
modify consent, EU routing restrictions, model selection or human legal review.
No hidden model reasoning is requested or stored by these added fields.

Run `python examples/audit_model_provenance_demo.py` without credentials.
The repository overview remains `python examples/minimal_demo.py`.
Run `python -m pytest tests/test_audit_model_provenance.py` for snapshot stability,
privacy, provider metadata and failure coverage. Adapter/routing regressions:
`python -m pytest tests/test_azure_foundry_client.py tests/test_ollama_client.py api/aijuristiction-api/tests/test_ai_model_routing.py`.

Real combined E2E must inspect each executed model operation's policy snapshot,
verify the actual provider/model route and source citations, then change a
synthetic route policy and confirm the first trace retains its earlier digest.
Use the #856 local PostgreSQL/API/MCP/browser setup and approved real model.
This branch's real-provider provenance acceptance is pending; unit tests are not
final E2E evidence. Retain only sanitized manifests/screenshots under ignored
`runs/` for at most seven days and delete synthetic case/route records afterwards.
