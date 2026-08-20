# Architecture Conformance Review Method

Use this matrix:

| Baseline requirement/decision | Authority | Implementation evidence | Result | Finding/action |
|---|---|---|---|---|
| <requirement> | <artifact link/status> | <file:line, test, config, runtime evidence> | <classification> | <action> |

Severity:

- `Critical`: credible compliance, safety, security, or irreversible data risk; stop release.
- `High`: violates an accepted decision or core requirement; resolve before release unless authorized exception exists.
- `Medium`: material drift, missing quality control, or stale artifact that can mislead implementation/operations.
- `Low`: clarity, traceability, or maintainability weakness without immediate behavioral impact.

Review at minimum: functional scope, component responsibilities, interfaces/dependencies, data lifecycle, trust boundaries, deployment/runtime, failure/recovery, observability, quality-attribute tests, GDPR safeguards, EU AI Act transparency/traceability/oversight, and documentation links.

An exception needs scope, rationale, risk, owner, expiry/review date, and authoritative approval evidence.
