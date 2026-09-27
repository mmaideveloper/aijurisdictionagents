#!/usr/bin/env bash
# Called only from the exact-SHA gated release. Preserve the old static web container.
set -euo pipefail
sha="${1:?release SHA}"
[[ "$sha" =~ ^[0-9a-f]{40}$ ]]
image="laws-tests-account:$sha"
backup="jurisdigta-web-before-laws-$sha"
docker build --build-arg VITE_API_BASE_URL=https://api.jurisdigta.eu \
  -t "$image" frontend/aijurisdictionfronend
if [[ "$(docker inspect jurisdigta-web --format '{{.Config.Image}}')" == "$image" ]]; then
  exit 0
fi
# Fail if the existing account frontend topology differs from the verified static service.
docker inspect jurisdigta-web | python3 -c '
import json,sys
c=json.load(sys.stdin)[0]
assert not c["Mounts"]
assert c["HostConfig"]["PortBindings"] == {"80/tcp":[{"HostIp":"127.0.0.1","HostPort":"8090"}]}
assert set(c["NetworkSettings"]["Networks"]) == {"bridge"}
'
if docker inspect "$backup" >/dev/null 2>&1; then
  echo 'Existing account rollback container requires operator review'; exit 1
fi
docker stop jurisdigta-web >/dev/null
docker rename jurisdigta-web "$backup"
restore() {
  docker rm -f jurisdigta-web >/dev/null 2>&1 || true
  docker rename "$backup" jurisdigta-web
  docker start jurisdigta-web >/dev/null
}
trap restore ERR
docker run -d --name jurisdigta-web --restart unless-stopped \
  --log-opt max-size=10m --log-opt max-file=3 -p 127.0.0.1:8090:80 "$image" >/dev/null
ready=0
for attempt in $(seq 1 30); do
  if curl -fsS http://127.0.0.1:8090/health >/dev/null; then ready=1; break; fi
  sleep 2
done
test "$ready" = 1
curl -fsS https://web.jurisdigta.eu/tests-authorize >/dev/null
trap - ERR
echo 'Account authorization frontend deployed; original container retained for rollback.'
