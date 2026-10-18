#!/usr/bin/env sh
set -eu

REPOSITORY_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
COMPOSE_FILE="$REPOSITORY_ROOT/docker-compose.qa-isolated.yml"
PROJECT_NAME=""
PRIVATE_DIRECTORY=$(mktemp -d)
chmod 0700 "$PRIVATE_DIRECTORY"

cleanup() {
  status=$?
  trap - EXIT HUP INT TERM
  if [ -n "$PROJECT_NAME" ]; then
    case "$PROJECT_NAME" in
      wgasuite_cleanup_test_*)
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
  case "$PRIVATE_DIRECTORY" in
    /tmp/tmp.*) rm -rf -- "$PRIVATE_DIRECTORY" ;;
    *)
      printf "Refusing to remove unexpected temporary directory.\n" >&2
      status=1
      ;;
  esac
  exit "$status"
}
trap cleanup EXIT HUP INT TERM

for command_name in curl diff docker python3 sha256sum tar; do
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
PROJECT_NAME="wgasuite_cleanup_test_${random_suffix}"
if [ -n "$(docker ps -aq --filter "label=com.docker.compose.project=$PROJECT_NAME")" ]; then
  printf "Refusing to reuse an existing Compose project.\n" >&2
  exit 1
fi
if [ -n "$(docker volume ls -q --filter "label=com.docker.compose.project=$PROJECT_NAME")" ]; then
  printf "Refusing to reuse an existing Compose project volume.\n" >&2
  exit 1
fi

QA_POSTGRES_DB="wgasuite_cleanup_test"
QA_POSTGRES_USER="wgasuite_cleanup_test"
QA_POSTGRES_PASSWORD=$(python3 -c 'import secrets; print(secrets.token_hex(32))')
QA_AUTH_SECRET_KEY=$(python3 -c 'import secrets; print(secrets.token_hex(48))')
QA_ADMIN_EMAIL="cleanup-test-admin@example.invalid"
QA_ADMIN_PASSWORD="Cleanup-$(python3 -c 'import secrets; print(secrets.token_hex(24))')!"
export QA_POSTGRES_DB QA_POSTGRES_USER QA_POSTGRES_PASSWORD QA_AUTH_SECRET_KEY
export QA_ADMIN_EMAIL QA_ADMIN_PASSWORD

compose() {
  docker compose \
    --project-name "$PROJECT_NAME" \
    --env-file /dev/null \
    --file "$COMPOSE_FILE" \
    "$@"
}

backend_private() {
  compose run --rm --no-deps \
    --user "$(id -u):$(id -g)" \
    --volume "$PRIVATE_DIRECTORY:/private" \
    backend "$@"
}

printf "Starting disposable guarded-cleanup integration environment...\n"
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
    printf "Isolation failure: backend does not have a random loopback binding.\n" >&2
    exit 1
    ;;
esac
if [ "$published_port" = "127.0.0.1:8000" ]; then
  printf "Isolation failure: refusing the normal backend port.\n" >&2
  exit 1
fi

API_BASE_URL="http://$published_port"
DEVELOPMENT_ADMIN_EMAIL="$QA_ADMIN_EMAIL"
DEVELOPMENT_ADMIN_PASSWORD="$QA_ADMIN_PASSWORD"
WGASUITE_SMOKE_ISOLATED_PROJECT="$PROJECT_NAME"
export API_BASE_URL DEVELOPMENT_ADMIN_EMAIL DEVELOPMENT_ADMIN_PASSWORD
export WGASUITE_SMOKE_ISOLATED_PROJECT
"$REPOSITORY_ROOT/scripts/dev/smoke_api.sh" >/dev/null

backend_private python -c \
  'from app.db.session import SessionLocal; from app.models import Customer; s=SessionLocal(); s.add(Customer(name="Unrelated retained customer", slug="unrelated-retained-customer", status="active")); s.commit(); s.close()'

validation_nonce=$(python3 -c 'import secrets; print(secrets.token_hex(32))')
mkdir -m 0700 "$PRIVATE_DIRECTORY/rollback-validation"
compose exec -T postgres psql \
  --username "$QA_POSTGRES_USER" \
  --dbname "$QA_POSTGRES_DB" \
  --set ON_ERROR_STOP=1 \
  --set "validation_nonce=$validation_nonce" <<'SQL'
CREATE TABLE wgasuite_cleanup_validation_guard (nonce text PRIMARY KEY);
INSERT INTO wgasuite_cleanup_validation_guard (nonce) VALUES (:'validation_nonce');
SQL
compose run --rm --no-deps \
  --user "$(id -u):$(id -g)" \
  --volume "$PRIVATE_DIRECTORY:/private" \
  --env WGASUITE_CLEANUP_VALIDATION_MODE=isolated_committed_cleanup_test \
  --env "WGASUITE_CLEANUP_VALIDATION_NONCE=$validation_nonce" \
  backend python -m app.maintenance.synthetic_cleanup_dry_run \
  --manifest-dir /private/rollback-validation \
  --validate-cascade-rollback >/dev/null
compose exec -T postgres psql \
  --username "$QA_POSTGRES_USER" \
  --dbname "$QA_POSTGRES_DB" \
  --set ON_ERROR_STOP=1 \
  --command "DROP TABLE wgasuite_cleanup_validation_guard"

database_backup="$PRIVATE_DIRECTORY/database.dump"
compose exec -T postgres pg_dump \
  --username "$QA_POSTGRES_USER" \
  --dbname "$QA_POSTGRES_DB" \
  --format custom >"$database_backup"
chmod 0600 "$database_backup"
compose exec -T postgres createdb \
  --username "$QA_POSTGRES_USER" wgasuite_cleanup_restore_test
compose exec -T postgres pg_restore \
  --username "$QA_POSTGRES_USER" \
  --dbname wgasuite_cleanup_restore_test \
  --no-owner --no-privileges <"$database_backup"
restored_tables=$(compose exec -T postgres psql \
  --username "$QA_POSTGRES_USER" \
  --dbname wgasuite_cleanup_restore_test \
  --tuples-only --no-align \
  --command "SELECT count(*) FROM pg_tables WHERE schemaname = 'public'" | tr -d '[:space:]')
if [ "$restored_tables" -lt 1 ]; then
  printf "Database recovery verification found no restored tables.\n" >&2
  exit 1
fi
restored_fixture_sets=$(compose exec -T postgres psql \
  --username "$QA_POSTGRES_USER" \
  --dbname wgasuite_cleanup_restore_test \
  --tuples-only --no-align \
  --command "SELECT count(*) FROM customers WHERE notes = 'Created by scripts/dev/smoke_api.sh'" | tr -d '[:space:]')
restored_control_customers=$(compose exec -T postgres psql \
  --username "$QA_POSTGRES_USER" \
  --dbname wgasuite_cleanup_restore_test \
  --tuples-only --no-align \
  --command "SELECT count(*) FROM customers WHERE slug = 'unrelated-retained-customer'" | tr -d '[:space:]')
if [ "$restored_fixture_sets" -ne 1 ] || [ "$restored_control_customers" -ne 1 ]; then
  printf "Database recovery verification did not restore expected isolated data.\n" >&2
  exit 1
fi
compose exec -T postgres dropdb \
  --username "$QA_POSTGRES_USER" wgasuite_cleanup_restore_test

credential_source="$PRIVATE_DIRECTORY/credential-source"
credential_recovery="$PRIVATE_DIRECTORY/credential-recovery"
mkdir -m 0700 "$credential_source" "$credential_recovery"
printf "isolated recovery sentinel\n" >"$credential_source/synthetic-placeholder"
chmod 0600 "$credential_source/synthetic-placeholder"
credential_backup="$PRIVATE_DIRECTORY/credentials.tar.gz"
tar -czf "$credential_backup" -C "$credential_source" .
chmod 0600 "$credential_backup"
tar -xzf "$credential_backup" -C "$credential_recovery"
diff -qr "$credential_source" "$credential_recovery" >/dev/null

backend_private python -m app.maintenance.synthetic_cleanup_dry_run \
  --manifest-dir /private >/dev/null
manifest_path=$(find "$PRIVATE_DIRECTORY" -maxdepth 1 -type f \
  -name 'synthetic-cleanup-review-*.json' | head -n 1)
if [ -z "$manifest_path" ]; then
  printf "Review manifest was not created.\n" >&2
  exit 1
fi
manifest_name=$(basename "$manifest_path")
manifest_sha256=$(sha256sum "$manifest_path" | cut -d ' ' -f 1)

python3 - "$manifest_path" "$PRIVATE_DIRECTORY" <<'PY'
import hashlib
import json
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

manifest_path = Path(sys.argv[1])
directory = Path(sys.argv[2])
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
now = datetime.now(UTC)
expires_at = min(
    now + timedelta(minutes=10),
    datetime.fromisoformat(manifest["plan"]["expires_at"]),
)
candidate = manifest["plan"]["candidate_sets"][0]
manifest_sha256 = hashlib.sha256(manifest_path.read_bytes()).hexdigest()

def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

approval = {
    "schema_version": 1,
    "mode": "synthetic_cleanup_human_approval",
    "plan_digest": manifest["plan_digest"],
    "manifest_sha256": manifest_sha256,
    "approved_customer_ids": [candidate["customer_id"]],
    "approved_organization_ids": [candidate["organization_id"]],
    "approved_by": "isolated-integration-reviewer",
    "approval_reference": "isolated-integration-test-only",
    "approved_at": now.isoformat(),
    "expires_at": expires_at.isoformat(),
}
backup_created_at = (now - timedelta(minutes=1)).isoformat()
verified_at = now.isoformat()
attestation = {
    "schema_version": 1,
    "mode": "synthetic_cleanup_backup_attestation",
    "plan_digest": manifest["plan_digest"],
    "database_context_sha256": manifest["plan"]["database_context_sha256"],
    "backup_set_id": "isolated-integration-test-backups",
    "attested_by": "isolated-integration-runner",
    "attested_at": now.isoformat(),
    "database_backup": {
        "path": "/private/database.dump",
        "sha256": digest(directory / "database.dump"),
        "created_at": backup_created_at,
        "restore_verified_at": verified_at,
        "verification_reference": "disposable restored database table inventory",
    },
    "credential_backup": {
        "path": "/private/credentials.tar.gz",
        "sha256": digest(directory / "credentials.tar.gz"),
        "created_at": backup_created_at,
        "recovery_verified_at": verified_at,
        "verification_reference": "disposable archive extraction and comparison",
    },
    "cascade_validation": {
        "status": "passed_and_rolled_back",
        "verified_at": verified_at,
        "records_temporarily_removed": manifest["plan"]["impact_counts"][
            "records_expected_to_be_deleted"
        ],
        "audit_events_preserved_and_detached": manifest["plan"]["impact_counts"][
            "audit_events_expected_to_be_preserved_and_detached"
        ],
        "verification_reference": "disposable rollback-only cascade verification",
    },
}
for name, value in (("approval.json", approval), ("backup-attestation.json", attestation)):
    path = directory / name
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, sort_keys=True)
        handle.write("\n")
PY

approval_path="$PRIVATE_DIRECTORY/approval.json"
attestation_path="$PRIVATE_DIRECTORY/backup-attestation.json"
approval_sha256=$(sha256sum "$approval_path" | cut -d ' ' -f 1)
attestation_sha256=$(sha256sum "$attestation_path" | cut -d ' ' -f 1)
plan_digest=$(python3 -c \
  'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["plan_digest"])' \
  "$manifest_path")
customer_id=$(python3 -c \
  'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["plan"]["candidate_sets"][0]["customer_id"])' \
  "$manifest_path")
organization_id=$(python3 -c \
  'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["plan"]["candidate_sets"][0]["organization_id"])' \
  "$manifest_path")
confirmation="DELETE REVIEWED SYNTHETIC RECORDS $plan_digest"

cleanup_command() {
  backend_private python -m app.maintenance.synthetic_cleanup_execution execute \
    --manifest "/private/$manifest_name" \
    --manifest-sha256 "$manifest_sha256" \
    --plan-digest "$plan_digest" \
    --approval /private/approval.json \
    --approval-sha256 "$approval_sha256" \
    --backup-attestation /private/backup-attestation.json \
    --backup-attestation-sha256 "$attestation_sha256" \
    --approve-customer "$customer_id" \
    --approve-organization "$organization_id" \
    --confirmation "$confirmation"
}

backend_private python -m app.maintenance.synthetic_cleanup_execution reconcile \
  --manifest "/private/$manifest_name" \
  --manifest-sha256 "$manifest_sha256" \
  --plan-digest "$plan_digest" | grep -q '"status": "not_committed"'

backend_private python -c \
  'from app.db.session import SessionLocal; from app.models import Customer, Organization; from app.maintenance.synthetic_record_analysis import SMOKE_MARKER; from sqlalchemy import select; s=SessionLocal(); c=s.scalar(select(Customer).where(Customer.notes == SMOKE_MARKER)); s.add(Organization(customer_id=c.id, name="Cleanup drift sentinel", description="isolated test drift")); s.commit(); s.close()'
if cleanup_command >"$PRIVATE_DIRECTORY/drift-attempt.log" 2>&1; then
  printf "Cleanup did not refuse post-plan relationship drift.\n" >&2
  exit 1
fi
backend_private python -c \
  'from app.db.session import SessionLocal; from app.models import Organization; from sqlalchemy import delete; s=SessionLocal(); s.execute(delete(Organization).where(Organization.name == "Cleanup drift sentinel")); s.commit(); s.close()'

compose exec -T postgres psql \
  --username "$QA_POSTGRES_USER" \
  --dbname "$QA_POSTGRES_DB" \
  --set ON_ERROR_STOP=1 <<'SQL'
CREATE FUNCTION refuse_cleanup_commit_marker() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.action = 'maintenance.synthetic_cleanup.committed' THEN
    RAISE EXCEPTION 'isolated rollback test';
  END IF;
  RETURN NEW;
END;
$$;
CREATE TRIGGER refuse_cleanup_commit_marker
BEFORE INSERT ON audit_events
FOR EACH ROW EXECUTE FUNCTION refuse_cleanup_commit_marker();
SQL
if cleanup_command >"$PRIVATE_DIRECTORY/rollback-attempt.log" 2>&1; then
  printf "Cleanup did not roll back after an injected SQL failure.\n" >&2
  exit 1
fi
backend_private python -m app.maintenance.synthetic_cleanup_execution reconcile \
  --manifest "/private/$manifest_name" \
  --manifest-sha256 "$manifest_sha256" \
  --plan-digest "$plan_digest" | grep -q '"status": "not_committed"'
compose exec -T postgres psql \
  --username "$QA_POSTGRES_USER" \
  --dbname "$QA_POSTGRES_DB" \
  --set ON_ERROR_STOP=1 <<'SQL'
DROP TRIGGER refuse_cleanup_commit_marker ON audit_events;
DROP FUNCTION refuse_cleanup_commit_marker();
SQL

set +e
cleanup_command >"$PRIVATE_DIRECTORY/concurrent-1.log" 2>&1 &
first_pid=$!
cleanup_command >"$PRIVATE_DIRECTORY/concurrent-2.log" 2>&1 &
second_pid=$!
wait "$first_pid"
first_status=$?
wait "$second_pid"
second_status=$?
set -e
if ! { [ "$first_status" -eq 0 ] && [ "$second_status" -ne 0 ]; } && \
   ! { [ "$first_status" -ne 0 ] && [ "$second_status" -eq 0 ]; }; then
  printf "Expected exactly one concurrent cleanup attempt to commit.\n" >&2
  printf "First attempt status=%s:\n" "$first_status" >&2
  tail -n 20 "$PRIVATE_DIRECTORY/concurrent-1.log" >&2
  printf "Second attempt status=%s:\n" "$second_status" >&2
  tail -n 20 "$PRIVATE_DIRECTORY/concurrent-2.log" >&2
  exit 1
fi
if [ "$first_status" -eq 0 ]; then
  winning_log="$PRIVATE_DIRECTORY/concurrent-1.log"
else
  winning_log="$PRIVATE_DIRECTORY/concurrent-2.log"
fi
expected_deleted=$(python3 -c \
  'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["plan"]["impact_counts"]["records_expected_to_be_deleted"])' \
  "$manifest_path")
expected_audits=$(python3 -c \
  'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["plan"]["impact_counts"]["audit_events_expected_to_be_preserved_and_detached"])' \
  "$manifest_path")
grep -q "\"records_deleted\": $expected_deleted" "$winning_log"
grep -q "\"audit_events_preserved_and_detached\": $expected_audits" "$winning_log"

if cleanup_command >"$PRIVATE_DIRECTORY/replay-attempt.log" 2>&1; then
  printf "Cleanup replay was not refused.\n" >&2
  exit 1
fi
backend_private python -m app.maintenance.synthetic_cleanup_execution reconcile \
  --manifest "/private/$manifest_name" \
  --manifest-sha256 "$manifest_sha256" \
  --plan-digest "$plan_digest" | grep -q '"status": "committed"'
backend_private python -m app.maintenance.synthetic_cleanup_execution reconcile \
  --manifest "/private/$manifest_name" \
  --manifest-sha256 "$manifest_sha256" \
  --plan-digest "$plan_digest" | grep -q '"status": "committed"'

backend_private python -c \
  'from app.db.session import SessionLocal; from app.models import Customer; from sqlalchemy import func, select; s=SessionLocal(); count=s.scalar(select(func.count()).select_from(Customer).where(Customer.slug == "unrelated-retained-customer")); s.close(); assert count == 1'

printf "Guarded cleanup integration passed in disposable PostgreSQL; resources will be removed.\n"
