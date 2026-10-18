#!/usr/bin/env sh
set -eu

REPOSITORY_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
PRIVATE_DIRECTORY="$REPOSITORY_ROOT/backend/app/maintenance/.private"

install -d -m 0700 "$PRIVATE_DIRECTORY"
chmod 0700 "$PRIVATE_DIRECTORY"

docker compose exec -T \
  --user "$(id -u):$(id -g)" \
  backend \
  python -m app.maintenance.synthetic_cleanup_dry_run \
  --manifest-dir /app/app/maintenance/.private
