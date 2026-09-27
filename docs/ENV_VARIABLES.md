# Environment Profiles

`.env.example` is the key schema; it never contains real secrets. Developer files
`.env` and `.env.dev` are ignored. The encrypted USB attached to
`jurisdigta-server` is the authoritative shared value store.

## Classification

| Profile | File | Purpose | Required-key source |
|---|---|---|---|
| `local-core` | `.env` | Local API and agent development | `config/env_profiles.json` |
| `codex-agent` | `.env` | AI-agent implementation/testing | Extends `local-core` |
| `laws-collector` | `.env` | Production-style local laws collection | Extends `local-core` |
| `mcp-local` | `.env` | Local MCP transport/authentication | Extends `local-core` |
| `azure-dev` | `.env.dev` | Temporary Azure development infrastructure | Separate explicit profile |

Every key in `.env.example` is part of the schema. Keys listed as `required` in
the selected profile are blocking; all other schema keys are optional for that
profile. Optional inactive keys should be absent or commented, not active with
`unknown-variable`. Secret-like keys never receive guessed defaults.

## Web MFA reuse

`MFA_REUSE_WINDOW_HOURS=12` keeps a successful web MFA verification valid for
12 hours. Logging out still invalidates the active authenticated session, but a
subsequent password sign-in during that window does not require another MFA
code on an already verified browser. If a different browser requires device
verification and the account has TOTP enabled, the API returns an MFA challenge
offering both authenticator TOTP and email OTP. Completing either method verifies
that browser for `MCP_OTP_REUSE_WINDOW_HOURS` and avoids an email-only prompt.
Accounts without TOTP continue to use the email OTP device-verification flow.
Set `MFA_REUSE_WINDOW_HOURS=0` to require MFA on every sign-in. The API runtime
fallback remains `0` when the variable is absent or invalid.

## Commands

```powershell
.\scripts\sync_env_profile.ps1 -Mode Audit -Profile codex-agent -Strict
.\scripts\sync_env_profile.ps1 -Mode Bootstrap -Profile local-core
.\scripts\sync_env_profile.ps1 -Mode Pull -Profile codex-agent
.\scripts\sync_env_profile.ps1 -Mode Audit -Profile azure-dev -EnvFilePath .env.dev -Strict
```

Output contains key names and states only. `Pull` uses pinned SSH host
verification, downloads to a temporary protected location, merges atomically,
validates, restores the previous local file on failure, and removes temporary
files. There is no developer push mode.

## Real-model E2E credentials

The optional `E2E_AZURE_FOUNDRY_*` keys are branch-local inputs for
`scripts/bootstrap_e2e_model_credentials.py`. They are deliberately separate from embedding
configuration and are copied into the local API database only after encryption. Keep them in the
ignored `.env`; `.env.example`, logs, manifests, screenshots, CI artifacts, and Git must contain
only placeholders or redacted metadata.

Use exactly one authentication value: `E2E_AZURE_FOUNDRY_API_KEY` or
`E2E_AZURE_FOUNDRY_AD_TOKEN`. `AI_MODEL_CREDENTIAL_ENCRYPTION_KEY` must also be resolved. The
bootstrap refuses SQLite, Azure/remote PostgreSQL, placeholder values, non-HTTPS endpoints, and
`LLM_PROVIDER=mock`. This prevents an E2E preparation command from writing the imported credential
to production or claiming a mock call as real-model evidence.

## USB layout

The encrypted USB mount provides:

```text
/mnt/jurisdigta-backup/jurisdigta-env/profiles/
  local-core.env
  codex-agent.env
  laws-collector.env
  azure-dev.env
  mcp-local.env
```

Use `Deployment/server/install_env_usb_profile.sh` as a privileged operator.
The USB must already satisfy issue #395 encryption, mount, retention, integrity,
and recovery-key requirements. The runtime server file is an atomic materialized
copy, not another authority.

Audit events may record actor, profile, key name, result, and checksum/version.
They must never record values, prompts, documents, personal data, or legal-case
content. Revoke developer SSH access during offboarding and securely delete
local materialized files and backups.

## Laws tests dedicated configuration (#840)

`laws-tests/api/laws_tests/config.py` explicitly loads `.env-laws-test`, or the path selected
by `LAWS_TEST_ENV_FILE`. It never implicitly uses root `.env`/`.env.dev` for runtime secrets.
Root `.env.example` documents every key; actual dedicated files and backup variants are ignored
by Git and Docker. Missing/`unknown-variable` required values prevent startup.

Required keys: `LAWS_TEST_DATABASE_URL` (database exactly `laws-tests`),
`LAWS_TEST_IDENTITY_DATABASE_URL`, `LAWS_TEST_PUBLIC_URL`, `LAWS_TEST_AUTH_URL`,
`LAWS_TEST_ENVIRONMENT` (`development`, `test`, `production`), `AZURE_OPENAI_ENDPOINT`,
`AZURE_OPENAI_API_VERSION`, `AZURE_OPENAI_DEPLOYMENT`, `AZURE_OPENAI_API_KEY`.
Development/test databases must be loopback PostgreSQL; public production URLs must use HTTPS.
`LAWS_TEST_LOCAL_PASSWORD` is used only by the isolated local PostgreSQL bootstrap.
`LAWS_TEST_MIGRATION_DATABASE_URL` lives in the separate server-only `.env-laws-test.migration`.
`LAWS_TEST_IDENTITY_NETWORK` is a nonsecret Docker network in server `deployment.env`.
`LAWS_TEST_REQUIRED_CHECKS` is the GitHub exact-SHA additional check list (JSON string array).
`VITE_LAWS_TEST_PUBLIC_URL` is the only new browser build setting and is public, never a secret.

Production runtime: `/srv/jurisdigta/secrets/.env-laws-test`, UID 10840, mode 0600.
Migration file: same directory, root, 0600. Encrypted USB authoritative paths:
`/mnt/jurisdigta-backup/jurisdigta-env/profiles/laws-tests/{dev,prod}/.env-laws-test`.
The dev directory is restricted to the approved SSH operator; production files remain root-only.
`PYTHON_DOTENV_DISABLED=1` is set by the acceptance service launcher only after explicitly loading valid settings; this prevents the existing account API from implicitly reloading unresolved placeholders.
## Laws Tests public source connection

`LAWS_TEST_LAWS_DATABASE_URL`: collector PostgreSQL DSN, read only through the dedicated
production `laws_tests_reader` role. Stored solely in the authoritative encrypted-USB
laws-tests profiles and `.env-laws-test`. Development/test require loopback. Empty or
`unknown-variable` leaves the reader visibly unavailable; no shared or production fallback.
The server profile provisioner derives this connection without exporting secrets, and the
gated release applies SELECT-only permissions. The root `.env.example` documents the key
but the application reads its explicit dedicated profile.
