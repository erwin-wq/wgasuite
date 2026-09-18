.PHONY: check-env backend-checks docker-up docker-down db-upgrade smoke-api frontend-install frontend-dev

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
	@DEVELOPMENT_ADMIN_EMAIL="$$(docker compose exec -T backend printenv DEVELOPMENT_ADMIN_EMAIL)" \
	DEVELOPMENT_ADMIN_PASSWORD="$$(docker compose exec -T backend printenv DEVELOPMENT_ADMIN_PASSWORD)" \
	./scripts/dev/smoke_api.sh

frontend-install:
	npm --prefix frontend ci

frontend-dev:
	npm --prefix frontend run dev
