#!/bin/sh
# Runs on the server (from deploy_to_server.ps1): build and start the stack, wait for
# the API health check, then load the labelled synthetic demonstration data.
set -eu
cd /opt/osrip/src
chmod 600 deploy/.env
compose() { docker compose -f deploy/docker-compose.yml --env-file deploy/.env "$@"; }

compose up -d --build

status=""
for _ in $(seq 1 60); do
  status=$(docker inspect -f '{{.State.Health.Status}}' osrip-api-1 2>/dev/null || true)
  [ "$status" = "healthy" ] && break
  sleep 5
done
echo "api health: ${status:-unknown}"
[ "$status" = "healthy" ] || { compose logs --tail 80 api migrate; exit 1; }

compose run --rm api python -m app.cli seed-synthetic
compose ps
