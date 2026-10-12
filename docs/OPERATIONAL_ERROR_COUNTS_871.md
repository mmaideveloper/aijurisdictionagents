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

## Selected Grafana range (#897)

The Errors dashboard's Total Errors now uses an instant Loki
`sum(count_over_time(... [$__range]))` query at the selected range's end.
Previously it reduced `sum(jurisdigta_errors_window)` to its latest sample;
that gauge represents the exporter's fixed status window and cannot count
events in a user-selected 5-minute or 6-hour interval. Never sum or apply
`increase` to this gauge: overlapping windows would miscount events.

The Application Performance top-row error stat (formerly Errors In Status
Window, the 1.12k panel) uses the same query and is renamed Errors In Selected
Range. The dashboard time picker controls both totals; the Usage window
variable still controls its separate AI usage panels. The runnable contract
check validates that both error stats share the query and instant evaluation.

Total Errors shares the System Logs operational failure filter and counts
matching lines across Docker and file sources. It includes retries and
traceback lines, not unique incidents. Source charts/tables retain their
fixed status windows and are explicitly labelled accordingly. Loki retention
and ingestion completeness bound historical coverage. No data is left visible
instead of substituting zero; inspect Loki ingestion and telemetry health.
Equal counts can still be correct when no additional failures occurred.

Runnable contract check (no Python environment needed):
`powershell -File examples/grafana_error_range_demo.ps1`.
Optionally pass `-LokiUrl http://127.0.0.1:3100` on the monitoring host to
compare 5m and 6h aggregates at the same end timestamp. Default application
example remains `python examples/minimal_demo.py`.

Roll out the provisioned JSON through the normal reviewed deployment after
all applicable exact-commit checks succeed. Confirm both ranges in Grafana and
retain a sanitized screenshot/manifest under ignored runs/artifacts for seven
days. Roll back by restoring the prior dashboard JSON. This change introduces
no personal-data fields, labels, consent, retention, or legal-output changes;
existing GDPR/EU AI Act access controls and human oversight remain applicable.
