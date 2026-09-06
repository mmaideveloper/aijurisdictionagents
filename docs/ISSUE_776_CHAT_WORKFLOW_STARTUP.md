# Issue #776: chat workflow startup timeout

## Root cause

Case-backed chat performs document-chunk retrieval before `PrimaryLangGraphRouter` and before the
workflow creates `langgraph_run_started`. Semantic ranking called
`get_embedding_client().embed_texts(...)` synchronously without a deadline. When local Hugging Face
initialization or a cloud embedding request did not return, the worker never reached the router.
The SSE consumer independently had no terminal deadline, so it emitted keepalive and `still_working`
events forever.

Two downstream defects became visible after the request could progress again:

- the primary router ignored a valid persisted case catalog selection and could send an explicitly
  assigned case through probabilistic generic classification instead of its pinned workflow;
- the frontend normalized typed presentation metadata inside an external-store selector, returning a
  fresh object on every snapshot and causing React's maximum-update-depth guard to empty the chat
  viewport. The case-thread cache key also omitted content/presentation shape changes.

The PostgreSQL launcher was not causal, but the setup complication is confirmed: when a local
container already exists, `start-postgres` replaces the database name from an explicit branch-specific
`-DbCloud` URI with the container's default. Direct Uvicorn startup against the intended database
reproduced the pre-router embedding boundary. The isolated launcher fix is tracked in [#779](https://github.com/mmaideveloper/aijurisdictionagents/issues/779).

## Deterministic reproduction and event sequence

Run the synthetic regression from the repository root:

```powershell
.\conda\python.exe -m pytest api/aijuristiction-api/tests/test_chat.py -q `
  -k "case_document_embedding_timeout_falls_back_before_langgraph_start or stream_read_user_has_terminal_timeout_and_done_signal"
```

The reproduction uses only synthetic text and a blocking fake embedding client. Its sanitized
timeline is:

| Relative timestamp | Correlation/request scope | Event | Timeout state |
| --- | --- | --- | --- |
| `T+00.000s` | synthetic test IDs | `case_document_query_embedding:started` | deadline active |
| `T+00.020s` | same IDs | `case_document_query_embedding:timed_out` | `case_embedding_timeout`; lexical fallback |
| next transition | same IDs | primary router / `langgraph_run_started` is no longer blocked by embedding initialization | embedding deadline cleared |
| terminal guard only | same IDs | SSE `error`, then `done(status=failed)` | `chat_workflow_timeout` |

API startup now records metadata-only stage durations. In the final local run, checkpoint pool opening
took 110 ms, checkpoint schema setup took 5 ms, and 62 default assignments took 18.85 seconds. These
markers distinguish expected initialization work from a request-path stall without logging case data.

The events contain IDs, counts, durations, model metadata, states, and bounded reason codes only.
They do not contain prompts, case/document content, retrieved text, credentials, tokens, or
connection strings.

## Runtime behavior

- `CHAT_EMBEDDING_TIMEOUT_SECONDS` defaults to 60 seconds. Timeout, provider failure, or an empty
  embedding result records a sanitized reason and continues with lexical-only chunk ranking.
- `CHAT_STREAM_TERMINAL_TIMEOUT_SECONDS` defaults to 660 seconds. If any unexpected dependency still
  blocks the worker, the stream marks the session failed and emits exactly one privacy-safe `error`
  followed by one `done` event. The response includes correlation and request IDs for support.
- Model adapter, MCP, workflow-tool, and LangGraph termination timeouts remain independently bounded
  by their existing policies.

These controls are privacy-by-design safeguards: semantic retrieval is optional, failure does not
silently change the configured chat model, and legal output still requires the existing human-review
and external-provider transparency notices.

## Real local acceptance

Final acceptance uses the configured Azure Foundry model, local PostgreSQL with current
migrations, deterministic synthetic case/law data, and the full frontend → API → MCP → PostgreSQL →
LangGraph → presentation path. Record the actual provider/model, database name, pinned graph/flow
versions, ordered events, expected/observed node path, and source IDs in the sanitized manifest.
Retain the manifest and final-state screenshot under ignored `runs/` or `artifacts/` storage for no
more than seven days, following `docs/E2E_TEST_EVIDENCE_RULE.md`.

The final run `issue-716-langgraph-tools-20260906T132933Z-f440493e` passed with Azure Foundry
`gpt-4o-mini`, `legal_document_workflow@4`, flow `sk.civil.payment_confirmation@5`, synthetic source
`issue-635-civil-code`, consented `registeradries_address_validate`, and ordered events from
`langgraph_run_started` through `workflow_terminated`. It produced a validated PDF, rendered first
page, stable presentation screenshot, and sanitized result manifest under ignored
`runs/e2e/issue-716-langgraph-tools/` storage.

After preparing the isolated `issue_776_e2e` and `laws_issue_776_e2e` databases with the approved
helpers, start the real local API and MCP services without printing credentials:

```powershell
.\conda\python.exe scripts\run_issue_776_e2e_services.py --api-port 8082 --mcp-port 8072
```

The launcher disables raw LLM I/O logging, enables offline cached embedding initialization, uses an
ephemeral in-memory MCP shared secret, health-checks both services, and stores service logs only under
ignored `runs/e2e/issue-776-chat-startup/` evidence. It fails before launch when either requested
loopback port is already occupied, preventing a health response from another worktree from being
mistaken for the service under test.
