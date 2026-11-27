#!/bin/sh
# Runs on the server (from deploy_to_server.ps1): build and start the stack and wait for the
# API health check. No data is loaded: the production database holds only what the team
# restores or publishes through the reviewed import workflow (docs/CENTRAL_HOSTING_EN.md).
# The labelled synthetic demonstration data is loaded only when explicitly asked for, on a
# demonstration server: OSRIP_LOAD_SYNTHETIC_DEMO_DATA=1 sh deploy/remote_up.sh
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

if [ "${OSRIP_LOAD_SYNTHETIC_DEMO_DATA:-0}" = "1" ]; then
  echo "Loading the labelled SYNTHETIC demonstration data (explicitly requested)."
  compose run --rm api python -m app.cli seed-synthetic
else
  echo "No demonstration data loaded (default). Restore or publish approved data separately."
fi
compose ps
