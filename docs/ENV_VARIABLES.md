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
