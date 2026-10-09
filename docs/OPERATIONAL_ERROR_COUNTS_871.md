# Operational failure counts (#871)

Operational classification uses severity and failure outcomes, not a substring
search for `error`. INFO success records containing `error=null` or
`failed_laws=0` are not failures. ERROR/FATAL/CRITICAL, nonzero failure summaries,
unstructured failure messages and exception/traceback records remain visible.

Server fallback `error_count` counts failure events in the bounded log tail,
deduplicating identical lines and collapsing unprefixed traceback continuation.
`log_event_counts` exposes separate failure, retry, access_denied, success and
unknown counts. Status alone cannot establish whether an authorization denial
was expected: investigate authenticated-session errors through protected logs;
never weaken OAuth or hide the security signal. Explicit authenticated denials
are failures. Unknown does not mean healthy.

The Loki dashboard uses the same RE2-compatible failure signature to count
matching **lines**, including retries, rather than claiming unique incidents.
Docker-prefixed tracebacks and distinct attempts can produce multiple lines.
Use correlation/time/source context for incident investigation; never publish
user identifiers as metric labels. Log alias/Docker-copy deduplication is handled
by #870. Raw keyword searching remains in Grafana Explore. Historical Loki
counts do not change retroactively into unique-incident counts.

Validate with `python -m pytest tests/test_operational_log_events.py
tests/test_server_monitoring.py`. Run `python examples/operational_log_counts_demo.py`;
default: `python examples/minimal_demo.py`. Fixtures contain synthetic metadata
only. Compare a fixed window before/after the dashboard filter and verify all
known actual failures remain visible; retain the sanitized aggregate manifest
under ignored runs/artifacts for at most seven days. Roll back dashboard/filter
code if genuine failures disappear; never alter stored history to reduce counts.

No model, legal-output, consent or authentication contract changes. Existing
access control, data minimization, retention and human oversight remain intact.
