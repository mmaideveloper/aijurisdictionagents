# GitHub-hosted real-model acceptance (#931)

`laws-tests-real-e2e` runs on a fresh GitHub-hosted Ubuntu VM with pgvector/PostgreSQL 16,
Python 3.13, Node 24 and Playwright Chromium. The same shared-account password/email-OTP,
law-reader and private-bank browser scenarios run against real loopback services and a
real Azure Foundry `gpt-5-mini` deployment. No laptop, Edge, local interpreter path, SSH,
server USB mount or production credential is required by the hosted job.

The privileged job remains manual (`workflow_dispatch`, `run_real_e2e=true`) in the protected
GitHub `test` Environment. Dispatch only reviewed refs in this repository; never fork code.
Dependency installation runs before the model secrets are injected into the acceptance step.
The four `E2E_AZURE_FOUNDRY_*` API-key settings are GitHub Environment secrets, backed by a
test-only Azure resource. The existing approved laptop E2E importer reads the production API
credential and must not be used to populate these hosted secrets.

The launcher creates ephemeral configuration files with owner-only permissions, generates
a fresh model-credential encryption key and synthetic account passwords, applies migrations,
uses the existing loopback-only encrypted credential bootstrap with real model verification,
and exercises the actual frontend/API/MCP/worker processes. It refuses existing config files
and non-hosted/non-Linux execution. Each job gets its own PostgreSQL service; fixture UUIDs
identify synthetic records. Services stop and fixture cleanup runs on success/failure.
GitHub destroys the VM and database service after the job, including on cancellation.

Upload only `runs/issue840/evidence`, `runs/issue924/evidence` and
`runs/hosted-e2e/evidence` for 14 days. Never upload private logs, `.env` files, database data,
account/device proof files, OTPs, passwords or tokens. Failure diagnostics contain exception
class names only. `cleanupPassed` is separate from functional acceptance status; failed
acceptance is never considered release evidence. Screenshots and retained synthetic PDFs
come from actual browser/worker operations, without route/model/database mocks.

Minimal runnable hosted example (after the Environment secrets are installed):

```powershell
gh workflow run laws_tests_validate.yml --ref main -f run_real_e2e=true
```

Offline launcher checks from the repository root:

```powershell
.\conda\python.exe -m pytest laws-tests/tests/test_hosted_acceptance.py -q
python examples/minimal_demo.py
```

The old PowerShell launchers remain available for explicit local development. Windows uses
Edge; Linux uses installed Chromium. Hosted jobs supply `LAWS_TEST_E2E_PYTHON` internally
from the active interpreter. The old GitHub Environment interpreter-path variable is unused.

Production remains a separate `LawsTest-Self-Managed-Prod-deploy` job on `jurisdigta-server`.
All configured checks, including the real-E2E job, must succeed for the exact release SHA.
No check names or release gates are removed. Merge acceptance and release acceptance are
distinct: dispatch the real suite again on the final merged commit before production.
