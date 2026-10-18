.PHONY: check-env backend-checks docker-up docker-down db-upgrade smoke-api \
	synthetic-cleanup-dry-run synthetic-cleanup-validate-restore frontend-install frontend-dev

check-env:
	./scripts/dev/check_environment.sh

backend-checks:
	./scripts/dev/run_backend_checks.sh

docker-up:
	docker compose up -d --build

docker-down:
	docker compose down

db-upgrade:
	docker compose exec backend alembic upgrade head
	docker compose exec backend python -m app.configure_development_admin

smoke-api:
	./scripts/dev/smoke_api_isolated.sh

synthetic-cleanup-dry-run:
	./scripts/dev/synthetic_cleanup_dry_run.sh

synthetic-cleanup-validate-restore:
	@test -n "$(BACKUP_PATH)" || (echo "Set BACKUP_PATH to a private PostgreSQL dump." >&2; exit 1)
	./scripts/dev/validate_synthetic_cleanup_restore.sh "$(BACKUP_PATH)"

frontend-install:
	npm --prefix frontend ci

frontend-dev:
	npm --prefix frontend run dev
