from __future__ import annotations

from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def test_default_smoke_target_uses_only_the_isolated_runner():
    makefile = (REPOSITORY_ROOT / "Makefile").read_text()
    smoke_target = makefile.split("smoke-api:", maxsplit=1)[1].split("\n\n", maxsplit=1)[0]

    assert "smoke_api_isolated.sh" in smoke_target
    assert "docker compose exec" not in smoke_target
    assert "printenv" not in smoke_target


def test_isolated_compose_has_no_database_port_or_google_credential_mount():
    compose = (REPOSITORY_ROOT / "docker-compose.qa-isolated.yml").read_text()
    postgres_section, backend_section = compose.split("  backend:", maxsplit=1)

    assert "ports:" not in postgres_section
    assert "127.0.0.1::8000" in backend_section
    assert "GOOGLE_WORKSPACE_CONNECTOR_ENABLED: \"false\"" in backend_section
    assert "empty-google-credentials" in backend_section
    assert "/secrets/google" not in compose
    assert "google_workspace_credentials" not in compose
    assert "postgres_data" not in compose.replace("qa_postgres_data", "")


def test_private_cleanup_manifests_are_excluded_from_backend_images():
    dockerignore = (REPOSITORY_ROOT / "backend/.dockerignore").read_text().splitlines()

    assert "app/maintenance/.private/" in dockerignore


def test_backend_image_normalizes_source_read_permissions_before_non_root_user():
    dockerfile = (REPOSITORY_ROOT / "backend/Dockerfile").read_text()

    assert "chmod -R u=rwX,go=rX /app/app /app/alembic" in dockerfile
    assert dockerfile.index("chmod -R u=rwX,go=rX") < dockerfile.index("USER wgasuite")


def test_isolated_runner_has_project_scoped_cleanup_and_random_binding_checks():
    runner = (REPOSITORY_ROOT / "scripts/dev/smoke_api_isolated.sh").read_text()

    assert 'PROJECT_NAME="wgasuite_smoke_${random_suffix}"' in runner
    assert "down --volumes --remove-orphans --rmi local" in runner
    assert 'published_port=$(compose port backend 8000)' in runner
    assert 'port_number" = "8000' in runner
    assert "docker volume prune" not in runner
    assert "docker system prune" not in runner


def test_fixture_writer_refuses_direct_or_normal_stack_execution():
    smoke_script = (REPOSITORY_ROOT / "scripts/dev/smoke_api.sh").read_text()
    first_request = smoke_script.index('request_json "GET" "/health"')

    assert smoke_script.index("WGASUITE_SMOKE_ISOLATED_PROJECT") < first_request
    assert smoke_script.index("http://127.0.0.1:8000") < first_request
    assert "/delegates" not in smoke_script
    assert "/members" not in smoke_script
    assert "/status" not in smoke_script


def test_committed_cleanup_test_is_scoped_to_disposable_infrastructure():
    runner = (
        REPOSITORY_ROOT / "scripts/dev/test_synthetic_cleanup_isolated.sh"
    ).read_text()

    assert 'PROJECT_NAME="wgasuite_cleanup_test_${random_suffix}"' in runner
    assert "docker-compose.qa-isolated.yml" in runner
    assert "down --volumes --remove-orphans --rmi local" in runner
    assert 'published_port=$(compose port backend 8000)' in runner
    assert "empty isolated credential archive" not in runner
    assert "docker volume prune" not in runner
    assert "docker system prune" not in runner
    assert "docker compose down -v" not in runner
