# JurisDigta Environment Sync

This runbook defines how workstation `.env` files are aligned with `.env.example`
and copied to the self-managed `jurisdigta-server`.

## Rule

- `.env.example` is the committed schema for expected environment variables.
- `.env` is local-only and ignored by Git.
- When `.env.example` gains a key, add that key to local `.env` with
  `unknown-variable` until the real value is known.
- The full local `.env` may be copied to `jurisdigta-server`, but only over SSH.
- The server runtime file is `/srv/jurisdigta/secrets/jurisdigta.env`.
- The server file must stay outside Git and use restrictive permissions.
- New task worktrees should be created with `.\scripts\new_task_worktree.ps1` so
  each worktree gets its own ignored `.env` plus `.\conda\python.exe`.
- The optional shared workstation seed is
  `%USERPROFILE%\.jurisdigta\aijurisdictionagents.env`; it is local-only,
  outside Git, and must be moved to another computer only through an approved
  encrypted/operator-controlled channel.

The `unknown-variable` placeholder is intentional. Local startup and sync checks
can warn when a required value still needs a real secret without inventing a
default or silently switching providers.

## New Worktrees

The worktree helper prepares both Python and local configuration:

```powershell
.\scripts\new_task_worktree.ps1 `
  -Branch codex/issue-123-short-name `
  -WorktreePath C:\Users\maton\.codex\worktrees\issue-123-short-name\aijurisdictionagents
```

It seeds the new worktree `.env` from the current checkout `.env` when present,
then from `%USERPROFILE%\.jurisdigta\aijurisdictionagents.env` when present, and
finally appends any active `.env.example` keys that are still missing. Concrete
local defaults from active `.env.example` entries are copied as-is; missing
secret or placeholder values stay `unknown-variable`. The final worktree `.env`
is copied back to the shared seed for the next worktree.

Commented examples remain opt-in. This prevents local worktrees from silently
switching to `LLM_PROVIDER=mock` or trying to export traces to a local OTLP
collector just because those optional examples are documented.

For another computer, first place the approved local seed at the same path or
pass a machine-local seed explicitly:

```powershell
.\scripts\new_task_worktree.ps1 `
  -Branch codex/issue-123-short-name `
  -EnvSeedPath D:\secure-config\aijurisdictionagents.env
```

Do not source-control `.env`, `.env.*`, or the shared seed. For GDPR and EU AI
Act security-of-processing expectations, keep these files readable only by
approved operators and rotate any value exposed through an unapproved channel.

## Sync Command

From the repository root:

```powershell
.\scripts\sync_jurisdigta_env.ps1
```

The default command:

1. Reads keys from `.env.example`, including commented example assignments.
2. Adds any missing active keys to `.env` as `KEY=unknown-variable`.
3. Copies the SSH key pair selected from `E:\jurisdigta\ssh` into
   `%USERPROFILE%\.ssh\jurisdigta`.
4. Transfers the full local `.env` to
   `jurisdigta-server:/srv/jurisdigta/secrets/jurisdigta.env`.
5. Installs the server file with mode `600`.

If `/srv/jurisdigta/secrets` requires elevated privileges on the server, use:

```powershell
.\scripts\sync_jurisdigta_env.ps1 -UseSudo
```

If `E:\jurisdigta\ssh` contains more than one public key, choose the intended key:

```powershell
.\scripts\sync_jurisdigta_env.ps1 -SshPublicKeyPath E:\jurisdigta\ssh\id_ed25519.pub
```

On first connection to a verified local server, accept and store a previously
unknown host key explicitly:

```powershell
.\scripts\sync_jurisdigta_env.ps1 -AcceptNewHostKey
```

Do not use this switch if SSH reports a changed host key. A changed host key
requires operator review before sending secrets.

## Minimal Runnable Example

Dry-run the local `.env.example` comparison without copying SSH keys or touching
the server:

```powershell
.\examples\sync_jurisdigta_env_demo.ps1
```

Equivalent direct command:

```powershell
.\scripts\sync_jurisdigta_env.ps1 -SkipSshKeySync -SkipTransfer -DryRun
```

## Validation

After a real sync:

```powershell
ssh jurisdigta-server "test -f /srv/jurisdigta/secrets/jurisdigta.env && stat -c '%a %U %G %n' /srv/jurisdigta/secrets/jurisdigta.env"
ssh jurisdigta-server "grep -n '^.*=unknown-variable$' /srv/jurisdigta/secrets/jurisdigta.env || true"
```

The first command should show mode `600`. The second command should print only
keys that still need real values.

## Compliance Notes

This flow stores secrets in plaintext on a trusted local server, so access must
remain limited to approved operators. Do not paste `.env` contents into tickets,
logs, chats, screenshots, or GitHub issues. Rotate any token or password exposed
outside the workstation, approved vault, or `jurisdigta-server` secret path.

For GDPR security-of-processing expectations, keep transfer logs metadata-only,
minimize who can read `/srv/jurisdigta/secrets/jurisdigta.env`, and use human
review before changing production configuration that affects legal-risk outputs.
