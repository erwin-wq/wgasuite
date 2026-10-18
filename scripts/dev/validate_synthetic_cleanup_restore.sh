#!/usr/bin/env sh
set -eu

for command_name in docker python3 realpath stat; do
  if ! command -v "$command_name" >/dev/null 2>&1; then
    printf "Missing required command: %s\n" "$command_name" >&2
    exit 1
  fi
done
if ! docker compose version >/dev/null 2>&1; then
  printf "Missing required command: docker compose\n" >&2
  exit 1
fi

if [ "$#" -ne 1 ]; then
  printf "Usage: %s /absolute/path/to/postgresql-custom-format.dump\n" "$0" >&2
  exit 1
fi

REPOSITORY_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
COMPOSE_FILE="$REPOSITORY_ROOT/docker-compose.qa-isolated.yml"
BACKUP_PATH=$(realpath -- "$1")
PRIVATE_DIRECTORY="$REPOSITORY_ROOT/backend/app/maintenance/.private"
PROJECT_NAME=""

if [ ! -f "$BACKUP_PATH" ]; then
  printf "Backup is not a regular file.\n" >&2
  exit 1
fi
case "$BACKUP_PATH" in
  "$REPOSITORY_ROOT"/*)
    printf "Refusing a database backup stored inside the repository.\n" >&2
    exit 1
    ;;
esac
backup_mode=$(stat -c '%a' "$BACKUP_PATH")
if [ "$backup_mode" != "600" ]; then
  printf "Backup must have filesystem mode 0600; found %s.\n" "$backup_mode" >&2
  exit 1
fi

cleanup() {
  status=$?
  trap - EXIT HUP INT TERM
  if [ -n "$PROJECT_NAME" ]; then
    case "$PROJECT_NAME" in
      wgasuite_cleanup_validation_*)
        docker compose \
          --project-name "$PROJECT_NAME" \
          --env-file /dev/null \
          --file "$COMPOSE_FILE" \
          down --volumes --remove-orphans --rmi local >/dev/null 2>&1 || true
        ;;
      *)
        printf "Refusing cleanup for unexpected Compose project name.\n" >&2
        status=1
        ;;
    esac
  fi
  exit "$status"
}
trap cleanup EXIT HUP INT TERM

install -d -m 0700 "$PRIVATE_DIRECTORY"
chmod 0700 "$PRIVATE_DIRECTORY"

random_suffix=$(python3 -c 'import secrets; print(secrets.token_hex(8))')
PROJECT_NAME="wgasuite_cleanup_validation_${random_suffix}"
if [ -n "$(docker ps -aq --filter "label=com.docker.compose.project=$PROJECT_NAME")" ]; then
  printf "Refusing to reuse an existing Compose project.\n" >&2
  exit 1
fi
if [ -n "$(docker volume ls -q --filter "label=com.docker.compose.project=$PROJECT_NAME")" ]; then
  printf "Refusing to reuse an existing Compose project volume.\n" >&2
  exit 1
fi

QA_POSTGRES_DB="wgasuite_cleanup_validation"
QA_POSTGRES_USER="wgasuite_cleanup_validator"
QA_POSTGRES_PASSWORD=$(python3 -c 'import secrets; print(secrets.token_hex(32))')
QA_AUTH_SECRET_KEY=$(python3 -c 'import secrets; print(secrets.token_hex(48))')
QA_ADMIN_EMAIL="cleanup-validator@example.invalid"
QA_ADMIN_PASSWORD="Cleanup-$(python3 -c 'import secrets; print(secrets.token_hex(24))')!"
VALIDATION_NONCE=$(python3 -c 'import secrets; print(secrets.token_hex(32))')
export QA_POSTGRES_DB QA_POSTGRES_USER QA_POSTGRES_PASSWORD QA_AUTH_SECRET_KEY
export QA_ADMIN_EMAIL QA_ADMIN_PASSWORD

compose() {
  docker compose \
    --project-name "$PROJECT_NAME" \
    --env-file /dev/null \
    --file "$COMPOSE_FILE" \
    "$@"
}

printf "Restoring the backup into a disposable, non-published PostgreSQL service...\n"
compose config --quiet
compose up -d --wait postgres
compose exec -T postgres pg_restore \
  --username "$QA_POSTGRES_USER" \
  --dbname "$QA_POSTGRES_DB" \
  --no-owner \
  --no-privileges <"$BACKUP_PATH"

compose exec -T postgres psql \
  --username "$QA_POSTGRES_USER" \
  --dbname "$QA_POSTGRES_DB" \
  --set ON_ERROR_STOP=1 \
  --set "validation_nonce=$VALIDATION_NONCE" <<'SQL'
CREATE TABLE wgasuite_cleanup_validation_guard (
  nonce text PRIMARY KEY
);
INSERT INTO wgasuite_cleanup_validation_guard (nonce) VALUES (:'validation_nonce');
SQL

compose build backend
compose run --rm --no-deps \
  --user "$(id -u):$(id -g)" \
  --volume "$PRIVATE_DIRECTORY:/private" \
  --env WGASUITE_CLEANUP_VALIDATION_MODE=isolated_restored_backup \
  --env "WGASUITE_CLEANUP_VALIDATION_NONCE=$VALIDATION_NONCE" \
  backend \
  python -m app.maintenance.synthetic_cleanup_dry_run \
  --manifest-dir /private \
  --validate-cascade-rollback

printf "Rollback validation passed; disposable restore resources will now be removed.\n"
