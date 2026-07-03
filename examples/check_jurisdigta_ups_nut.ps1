param(
    [string]$SshConfig = "$env:USERPROFILE\.ssh\jurisdigta\config",
    [string]$SshKey = "$env:USERPROFILE\.ssh\jurisdigta\id_ed25519",
    [string]$Target = "jurisdigta-admin@192.168.1.25",
    [string]$UpsName = "eaton5p"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $SshConfig)) {
    throw "SSH config not found: $SshConfig"
}

if (-not (Test-Path -LiteralPath $SshKey)) {
    throw "SSH key not found: $SshKey"
}

$remote = @"
set -euo pipefail
echo "NUT service state"
systemctl is-enabled nut-driver@${UpsName}.service nut-server.service nut-monitor.service
systemctl is-active nut-driver@${UpsName}.service nut-server.service nut-monitor.service

echo
echo "NUT listener"
ss -ltnp | grep ':3493'

echo
echo "UPS telemetry"
upsc ${UpsName}@localhost | grep -E '^(battery\.charge|battery\.runtime|device\.mfr|device\.model|driver\.name|input\.voltage|ups\.load|ups\.mfr|ups\.model|ups\.status):'

echo
echo "Recent UPS notifications"
journalctl -t jurisdigta-ups -n 10 --no-pager || true
"@

$remote | ssh -F $SshConfig -i $SshKey -o BatchMode=yes -o ConnectTimeout=8 $Target "bash -s"
