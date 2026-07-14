#!/usr/bin/env bash
set -euo pipefail

profile="${1:-}"
source_file="${2:-}"
usb_root="${JURISDIGTA_ENV_USB_ROOT:-/mnt/jurisdigta-backup/jurisdigta-env/profiles}"
runtime_file="${JURISDIGTA_RUNTIME_ENV:-/srv/jurisdigta/secrets/jurisdigta.env}"

if [[ ! "$profile" =~ ^(local-core|codex-agent|laws-collector|azure-dev|mcp-local)$ ]]; then
  echo "Unsupported profile name." >&2
  exit 2
fi
if [[ ! -f "$source_file" ]]; then
  echo "Operator source file does not exist." >&2
  exit 2
fi
mountpoint -q "$(dirname "$(dirname "$usb_root")")" || { echo "Expected encrypted USB mount is unavailable." >&2; exit 3; }
install -d -m 0700 "$usb_root"
temporary="$(mktemp "$usb_root/.${profile}.XXXXXX")"
trap 'rm -f "$temporary"' EXIT
install -m 0600 "$source_file" "$temporary"
mv -f "$temporary" "$usb_root/$profile.env"

if [[ "$profile" == "local-core" ]]; then
  install -d -m 0700 "$(dirname "$runtime_file")"
  runtime_temporary="$(mktemp "$(dirname "$runtime_file")/.jurisdigta.env.XXXXXX")"
  install -m 0600 "$usb_root/$profile.env" "$runtime_temporary"
  mv -f "$runtime_temporary" "$runtime_file"
fi
echo "Installed profile $profile; values were not displayed."
