# Latest-log lifecycle (#870)

Scheduled wrappers atomically publish a relative latest symlink at job start and
completion. Retention uses `scripts/server/log_lifecycle.py` to repoint aliases
to retained same-service logs before removing expired history. A dangling alias
with no retained replacement is removed, making history unavailable rather than
fabricating an empty successful log. Existing retention limits remain in force.

Alloy excludes `*-latest.log` from discovery and collects dated logs once. The
court-worker file copy is excluded because Docker already supplies those events.
Other job files and Docker sources remain available. See the documented
[Alloy file exclusion contract](https://grafana.com/docs/alloy/latest/reference/components/local/local.file_match/).

Validate with `python -m pytest tests/test_log_lifecycle.py` on Linux and
`alloy validate Deployment/monitoring/alloy/config.alloy`. Native Windows
symlink privilege tests run in Linux Docker. Run `python
examples/log_lifecycle_demo.py`; the default remains `python
examples/minimal_demo.py`. Tests use synthetic files only.

Before gated rollout, inspect active log sources, regenerate scheduled and
retention wrappers and validate Alloy configuration. Continuous collector
freshness comes from Docker rather than an obsolete daily alias. Observe at
least three discovery scans plus a cleanup cycle. Roll back configuration and
wrappers if legitimate logs disappear. Retain history only within existing
retention/access policies; no customer content or secrets enter new telemetry.
