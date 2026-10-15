#!/bin/sh
# Nightly PostgreSQL dump for the "backup" service in docker-compose.yml.
# Writes to a temporary name first, so a failed dump never replaces a good one.
set -u
KEEP="${BACKUP_KEEP_DAYS:-14}"
while true; do
  name="/backups/osrip-$(date +%Y%m%d-%H%M%S).dump"
  if pg_dump -h db -U osrip -Fc osrip > "$name.partial"; then
    mv "$name.partial" "$name"
    echo "backup ok: $name ($(du -h "$name" | cut -f1))"
  else
    rm -f "$name.partial"
    echo "backup FAILED at $(date -u +%FT%TZ)" >&2
  fi
  # Prune dumps older than KEEP days.
  find /backups -name 'osrip-*.dump' -mtime "+$KEEP" -exec rm -f {} +
  sleep 86400
done
