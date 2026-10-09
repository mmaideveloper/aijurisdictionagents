# Legacy flow draft validation (#873)

Production traces identified `FlowPackCreateRequest` validation failures in
`FlowPackStore.create_version` for `positive_examples` (`too_short`). Legacy
routing metadata can contain an empty list although new create requests require
at least one example. Cloning a version previously raised an internal Pydantic
exception, producing a server error.

`POST /v1/flow-packs/{flow_key}/versions` now returns HTTP 422 with a safe
instruction to provide at least one `positive_examples` item when both the
source version and new request lack examples. An explicit valid list creates
a disabled draft normally; an explicit empty list remains invalid. The original
version is not rewritten, no examples are fabricated, and no partial draft is
inserted on failure. Existing admin/API authentication and lifecycle review
remain required. The same contract applies to direct API and any admin client;
chat, mobile and simulator legal generation are unchanged.

Run `scripts/validate_api.ps1` and `python -m pytest
api/aijuristiction-api/tests`. Focused reproduction:
`python -m pytest api/aijuristiction-api/tests/test_flow_packs_api.py
-k legacy_empty_examples`. Minimal synthetic schema example:
`python examples/flow_draft_validation_demo.py`; repository default remains
`python examples/minimal_demo.py`. Unit tests use isolated synthetic SQLite;
they are not real-model PostgreSQL/frontend acceptance evidence.

No database migration, new credentials/environment variables, consent purpose
or external model processing is introduced. Errors contain only a field name
and corrective instruction, without stored example values, prompts, personal
data or traceback details. Retain existing audit, human approval and deletion
controls. A gated rollout should verify a legacy clone gives 422, corrected
input gives a disabled draft, and the original stays unchanged. Rollback is
application-only; no data rollback is needed.
