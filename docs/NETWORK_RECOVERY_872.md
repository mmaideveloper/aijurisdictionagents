# Collector network recovery (#872)

The production review found historical temporary name-resolution failures in
laws collection and DNS timeout failures in blackbox probes. Both containers
use Docker's embedded resolver (`127.0.0.11`); this alone is expected, not a
configuration defect. Current collector activity was fresh. File-job noise
was also attributed to `mcp-trycloudflared.log`: tunnel control-stream failures
are a separate source and cannot all be classified as collector DNS errors.
No permanent resolver defect or common upstream outage was established.

The demonstrated code gap was that a transient DNS failure immediately aborted
an individual resource request, while a failed HTTP probe could be treated as a
missing law. Collector source opens now retry temporary DNS (`EAI_AGAIN`),
timeouts/connections and HTTP 408/429/5xx at most three times with exponential
backoff/jitter inside the original timeout budget. Retry-After is respected; if
it exceeds the remaining budget the original failure is retained for the next
worker cycle. Permanent DNS, auth, 404 and programming/storage errors are not
retried by this helper. Only a confirmed 404 probe marks a resource absent.
Persistent failures stay visible and do not move the sequential law cursor.

This does not change DNS servers, probe destinations, model routing or legal
retrieval contracts. Do not hardcode public resolvers or source IP addresses.
Diagnose resolution from the affected container and correlate time/source with
freshness and probe metrics. Escalate sustained failures or stale corpus data;
never label an unavailable source as up to date based on a failed network call.

Run `python -m pytest tests/test_laws_network_retry.py tests/test_laws_collector.py
tests/test_laws_collector_zip_import.py` and `python examples/laws_network_retry_demo.py`.
The default remains `python examples/minimal_demo.py`. Tests inject deterministic
synthetic failures before acceptance and do not claim real-model retrieval E2E.
No schema, credentials, infrastructure inputs or new environment variables are
introduced. Existing privacy/retention controls remain in force; no payloads or
secrets are logged by the retry helper. Gated rollout must observe source
recovery/cursor/freshness and probe success. Roll back code on throughput or
timeout regressions while preserving existing cursor records.
