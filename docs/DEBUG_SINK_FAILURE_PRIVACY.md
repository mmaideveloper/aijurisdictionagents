# Optional diagnostic failure privacy (#929)

The optional session debug sink must never prevent a chat response when its store is
unavailable. Its warning records only correlation/request identifiers and the exception
class. It omits exception messages, payloads, tracebacks and chained exceptions: a sink
failure can occur while handling a private chat failure, and `exc_info` would reveal both.
Use the identifiers to investigate store availability without recording source content.

This minimizes personal-data exposure under the existing GDPR/EU AI Act baseline; no new
data collection, model processing, retention period or automated decision is introduced.
Existing seven-day protected diagnostic retention remains unchanged.

Minimal runnable regression from the repository root:

```powershell
.\conda\python.exe -m pytest api/aijuristiction-api/tests/test_debug_trace_privacy.py -q
```

The fixture raises a synthetic store failure while handling a synthetic private exception
and asserts that neither exception text nor payload reaches logs. Full validation remains
`scripts/validate_api.ps1` and the API unit suite. General example: `python examples/minimal_demo.py`.
