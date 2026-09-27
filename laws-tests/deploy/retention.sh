#!/usr/bin/env bash
set -euo pipefail
sha=$(cat /srv/jurisdigta/laws-tests/current-sha)
[[ "$sha" =~ ^[0-9a-f]{40}$ ]]
set -a
source /srv/jurisdigta/laws-tests/deployment.env
set +a
export RELEASE_SHA="$sha"
docker compose -p laws-tests -f "/srv/jurisdigta/laws-tests/releases/$sha/laws-tests/deploy/compose.yml" exec -T api python -m laws_tests.cli purge
