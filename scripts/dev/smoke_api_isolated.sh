#!/usr/bin/env sh
set -eu

REPOSITORY_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
COMPOSE_FILE="$REPOSITORY_ROOT/docker-compose.qa-isolated.yml"
PROJECT_NAME=""

cleanup() {
  status=$?
  trap - EXIT HUP INT TERM

  if [ -n "$PROJECT_NAME" ]; then
    case "$PROJECT_NAME" in
      wgasuite_smoke_*)
        if [ "$status" -ne 0 ]; then
          docker compose \
            --project-name "$PROJECT_NAME" \
            --env-file /dev/null \
            --file "$COMPOSE_FILE" \
            logs --no-color --tail 100 2>/dev/null || true
        fi
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

for command_name in docker python3 curl; do
  if ! command -v "$command_name" >/dev/null 2>&1; then
    printf "Missing required command: %s\n" "$command_name" >&2
    exit 1
  fi
done
if ! docker compose version >/dev/null 2>&1; then
  printf "Missing required command: docker compose\n" >&2
  exit 1
fi

random_suffix=$(python3 -c 'import secrets; print(secrets.token_hex(8))')
PROJECT_NAME="wgasuite_smoke_${random_suffix}"
if [ -n "$(docker ps -aq --filter "label=com.docker.compose.project=$PROJECT_NAME")" ]; then
  printf "Refusing to reuse an existing Compose project.\n" >&2
  exit 1
fi
if [ -n "$(docker volume ls -q --filter "label=com.docker.compose.project=$PROJECT_NAME")" ]; then
  printf "Refusing to reuse an existing Compose project volume.\n" >&2
  exit 1
fi

QA_POSTGRES_DB="wgasuite_smoke"
QA_POSTGRES_USER="wgasuite_smoke"
QA_POSTGRES_PASSWORD=$(python3 -c 'import secrets; print(secrets.token_hex(32))')
QA_AUTH_SECRET_KEY=$(python3 -c 'import secrets; print(secrets.token_hex(48))')
QA_ADMIN_EMAIL="smoke-admin@example.invalid"
QA_ADMIN_PASSWORD="Smoke-$(python3 -c 'import secrets; print(secrets.token_hex(24))')!"
export QA_POSTGRES_DB QA_POSTGRES_USER QA_POSTGRES_PASSWORD QA_AUTH_SECRET_KEY
export QA_ADMIN_EMAIL QA_ADMIN_PASSWORD

compose() {
  docker compose \
    --project-name "$PROJECT_NAME" \
    --env-file /dev/null \
    --file "$COMPOSE_FILE" \
    "$@"
}

printf "Starting isolated API smoke environment (%s)...\n" "$PROJECT_NAME"
compose config --quiet
compose up -d --wait postgres
compose build backend
compose run --rm --no-deps backend alembic upgrade head
compose run --rm --no-deps backend python -m app.configure_development_admin
compose up -d --no-build --wait backend

published_port=$(compose port backend 8000)
case "$published_port" in
  127.0.0.1:[0-9]*) ;;
  *)
    printf "Isolation failure: backend was not bound to a random loopback port.\n" >&2
    exit 1
    ;;
esac
port_number=${published_port#127.0.0.1:}
case "$port_number" in
  ""|*[!0-9]*)
    printf "Isolation failure: backend port is not numeric.\n" >&2
    exit 1
    ;;
esac
if [ "$port_number" = "8000" ]; then
  printf "Isolation failure: refusing the normal WGASuite backend port.\n" >&2
  exit 1
fi

API_BASE_URL="http://$published_port"
DEVELOPMENT_ADMIN_EMAIL="$QA_ADMIN_EMAIL"
DEVELOPMENT_ADMIN_PASSWORD="$QA_ADMIN_PASSWORD"
WGASUITE_SMOKE_ISOLATED_PROJECT="$PROJECT_NAME"
export API_BASE_URL DEVELOPMENT_ADMIN_EMAIL DEVELOPMENT_ADMIN_PASSWORD
export WGASUITE_SMOKE_ISOLATED_PROJECT

"$REPOSITORY_ROOT/scripts/dev/smoke_api.sh"
printf "Isolated smoke resources will now be removed.\n"
