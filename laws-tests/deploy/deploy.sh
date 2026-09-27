#!/usr/bin/env bash
set -euo pipefail
release_sha="${1:?release SHA required}"
[[ "$release_sha" =~ ^[0-9a-f]{40}$ ]]
test -r /srv/jurisdigta/secrets/.env-laws-test
test -r /srv/jurisdigta/laws-tests/deployment.env
# This file contains only the reviewed network name and public routing configuration.
set -a
source /srv/jurisdigta/laws-tests/deployment.env
set +a
export RELEASE_SHA="$release_sha"
exec 9>/srv/jurisdigta/laws-tests/deploy.lock
flock -n 9 || { echo 'Another laws-tests deployment is active'; exit 1; }
root="/srv/jurisdigta/laws-tests/releases/$release_sha"
test "$(pwd)" = "$root"
mkdir -p /srv/jurisdigta/laws-tests/backups
chmod 700 /srv/jurisdigta/laws-tests/backups
docker build -f laws-tests/deploy/api.Dockerfile -t "laws-tests-api:$release_sha" .
docker build -f laws-tests/deploy/web.Dockerfile -t "laws-tests-web:$release_sha" .
docker build -f laws-tests/deploy/smoke.Dockerfile -t "laws-tests-smoke:$release_sha" .
compose=(docker compose -p laws-tests -f laws-tests/deploy/compose.yml)
# SQL backup and migration must succeed before replacing either application service.
"${compose[@]}" run --rm --no-deps --user root -v /srv/jurisdigta/laws-tests/backups:/backups \
  -v /srv/jurisdigta/secrets/.env-laws-test.migration:/run/secrets/migration.env:ro \
  api python /app/laws-tests/deploy/migrate_release.py "$release_sha"
"${compose[@]}" up -d --no-deps api
ready=0
for attempt in $(seq 1 30); do
  if "${compose[@]}" exec -T api python -c 'import urllib.request; urllib.request.urlopen("http://127.0.0.1:8000/api/health", timeout=5)' >/dev/null 2>&1; then ready=1; break; fi
  sleep 2
done
test "$ready" = 1
"${compose[@]}" up -d --no-deps web
curl --fail --silent --show-error https://tests.jurisigta.eu/api/health | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d=={"status":"ok","service":"laws-tests"}'
curl --fail --silent --show-error https://tests.jurisigta.eu/ >/dev/null
evidence="/srv/jurisdigta/laws-tests/evidence/$release_sha"
mkdir -p "$evidence"
chmod 700 "$evidence"
umask 077
synthetic=$(mktemp /srv/jurisdigta/laws-tests/.smoke-XXXXXX)
cleanup() {
  if test -s "$synthetic"; then
    "${compose[@]}" run --rm -T --no-deps --user root \
      -v /srv/jurisdigta/secrets/.env-laws-test.migration:/run/secrets/migration.env:ro \
      api python /app/laws-tests/deploy/smoke_identity.py cleanup < "$synthetic" || return 1
  fi
  rm -f "$synthetic"
}
trap cleanup EXIT
"${compose[@]}" run --rm -T --no-deps --user root \
  -v /srv/jurisdigta/secrets/.env-laws-test.migration:/run/secrets/migration.env:ro \
  api python /app/laws-tests/deploy/smoke_identity.py create > "$synthetic"
docker run --rm --ipc=host -v "$synthetic:/run/secrets/synthetic.json:ro" \
  -v "$evidence:/evidence" "laws-tests-smoke:$release_sha"
cleanup
trap - EXIT
printf '%s\n' "$release_sha" > "$evidence/sha.txt"
printf '%s\n' "$release_sha" > /srv/jurisdigta/laws-tests/current-sha
echo "Laws-tests release verified: $release_sha"
