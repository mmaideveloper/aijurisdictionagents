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

## Embedded monitoring queries (#902)

Grafana/Loki INFO query logs can contain the failure filter itself in `query=`.
Matching that diagnostic value counts successful queries as failures and creates
monitoring feedback noise. The shared classifier and all six dashboard failure
queries now remove complete quoted `query="..."` and JSON `"query": "..."`
fields before applying the existing severity/outcome filter. Escaped quotes are
handled; incomplete values stay visible. Unknown events stay unknown, and real
ERROR/FATAL/CRITICAL, failures, retries and authenticated denials outside query
metadata remain actionable. Traceback grouping uses the same normalized text.

This is query-time normalization, not deletion or an INFO/container allowlist.
Errors Only shows normalized messages; Recent Logs and Explore retain original
records. No other payload fields are removed. Grafana session-token rotation
warnings, Alloy removed-container errors and cAdvisor filesystem errors are not
silenced by this change; investigate those independently.

Run `python examples/operational_log_counts_demo.py` for synthetic query metadata
and real-failure examples, and `powershell -File
examples/grafana_error_range_demo.ps1` for the shared dashboard pipeline contract.
The default remains `python examples/minimal_demo.py`. Validate the Python
classifier and actual Loki pipeline with synthetic escaped/malformed query fields,
real errors after query fields, retry/traceback records and security outcomes.
With an isolated loopback Loki running, use `python
examples/operational_log_counts_demo.py --loki-url http://127.0.0.1:13102` to seed
ten synthetic records under a unique run label and assert seven failure lines.
Remove the task's isolated Loki/Grafana containers after capturing the dashboard
screenshot; never run the synthetic seed against production. This monitoring-only
path has no application database, legal retrieval or model call; model routing is
recorded as not applicable rather than claimed as real-model E2E acceptance.
Compare old/new live counts at a fixed end timestamp and retain aggregate evidence
under ignored `runs/` or `artifacts/` for at most seven days. Do not print raw logs.
Rollback the classifier and dashboard queries together if genuine failures vanish.
Production rollout still requires successful applicable checks for the exact SHA.
The change preserves GDPR data minimization and EU AI Act traceability/human
oversight, with existing access, retention and legal-output contracts unchanged.

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
