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

smoke-api:
	./scripts/dev/smoke_api.sh

frontend-install:
	npm --prefix frontend install

frontend-dev:
	npm --prefix frontend run dev
