from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from googleapiclient.errors import HttpError
from httplib2 import Response
from sqlalchemy.orm import Session

from app.connectors.google_workspace_credentials import DIRECTORY_ORGUNIT_READONLY_SCOPE
from app.connectors.google_workspace_errors import (
    GoogleWorkspaceError,
    GoogleWorkspaceErrorCode,
)
from app.services.google_workspace_orgunits import (
    GoogleWorkspaceOrganizationalUnits,
    OrganizationalUnitHierarchy,
    OrganizationalUnitTreeNode,
)
from app.services.google_workspace_user_lookup import GoogleWorkspaceUserLookupResult
from tests.test_customer_data_scoping import add_user, login_headers
from tests.test_google_workspace_connection import create_connector


class FakeRequest:
    def __init__(self, response: object) -> None:
        self.response = response
        self.execute_kwargs: dict[str, Any] | None = None

    def execute(self, **kwargs: Any) -> object:
        self.execute_kwargs = kwargs
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


class FakeOrgunitsResource:
    def __init__(self, responses: list[object]) -> None:
        self.responses = responses
        self.calls: list[dict[str, Any]] = []
        self.requests: list[FakeRequest] = []

    def _request(self, method: str, kwargs: dict[str, Any]) -> FakeRequest:
        request = FakeRequest(self.responses.pop(0))
        self.calls.append({"method": method, "kwargs": kwargs})
        self.requests.append(request)
        return request

    def list(self, **kwargs: Any) -> FakeRequest:
        return self._request("list", kwargs)

    def get(self, **kwargs: Any) -> FakeRequest:
        return self._request("get", kwargs)


class FakeDirectoryClient:
    def __init__(self, *responses: object) -> None:
        self.orgunits_resource = FakeOrgunitsResource(list(responses))
        self.closed = False

    def orgunits(self) -> FakeOrgunitsResource:
        return self.orgunits_resource

    def close(self) -> None:
        self.closed = True


class FakeClientFactory:
    def __init__(self, client: FakeDirectoryClient) -> None:
        self.client = client
        self.calls: list[dict[str, Any]] = []

    def for_directory_orgunits(self, **kwargs: Any) -> FakeDirectoryClient:
        self.calls.append(kwargs)
        return self.client


class FakeLookup:
    def __init__(self, customer_id: str = "google-customer-1") -> None:
        self.customer_id = customer_id
        self.calls: list[dict[str, Any]] = []

    def lookup(self, **kwargs: Any) -> GoogleWorkspaceUserLookupResult:
        self.calls.append(kwargs)
        return GoogleWorkspaceUserLookupResult(
            id="admin-1",
            customer_id=self.customer_id,
            full_name="Directory Administrator",
            primary_email="admin@example.com",
            aliases=[],
            non_editable_aliases=[],
            suspended=False,
            archived=False,
            org_unit_path="/",
            is_mailbox_setup=True,
            matched_by="primary_email",
        )


def unit(
    unit_id: str,
    name: str,
    path: str,
    parent_id: str | None = None,
    parent_path: str | None = None,
    description: str | None = None,
) -> dict[str, object]:
    value: dict[str, object] = {
        "orgUnitId": unit_id,
        "name": name,
        "orgUnitPath": path,
    }
    if parent_id is not None:
        value["parentOrgUnitId"] = parent_id
    if parent_path is not None:
        value["parentOrgUnitPath"] = parent_path
    if description is not None:
        value["description"] = description
    return value


ROOT = unit("id:root", "Example Workspace", "/")
ENGINEERING = unit(
    "id:engineering", "Engineering", "/Engineering", "id:root", "/", "Builders"
)
PLATFORM = unit(
    "id:platform",
    "Platform",
    "/Engineering/Platform",
    "id:engineering",
    "/Engineering",
)


def orgunit_service(
    db_session: Session,
    *responses: object,
    customer_id: str = "google-customer-1",
) -> tuple[GoogleWorkspaceOrganizationalUnits, FakeClientFactory, FakeLookup, UUID, Any]:
    connector, actor = create_connector(db_session)
    client = FakeDirectoryClient(*responses)
    factory = FakeClientFactory(client)
    lookup = FakeLookup(customer_id)
    service = GoogleWorkspaceOrganizationalUnits(
        db_session,
        factory,  # type: ignore[arg-type]
        lookup,  # type: ignore[arg-type]
    )
    return service, factory, lookup, connector.organization_id, actor


def test_list_uses_verified_customer_full_hierarchy_readonly_scope_and_no_retries(
    db_session: Session,
) -> None:
    service, factory, lookup, organization_id, actor = orgunit_service(
        db_session,
        {"organizationUnits": [PLATFORM, ROOT, ENGINEERING]},
    )

    result = service.list_hierarchy(actor=actor, organization_id=organization_id)

    assert result.total == 3
    assert result.roots[0].id == "id:root"
    assert result.roots[0].children[0].id == "id:engineering"
    assert result.roots[0].children[0].children[0].id == "id:platform"
    assert result.roots[0].children[0].description == "Builders"
    assert lookup.calls[0]["email"] == "admin@example.com"
    assert factory.calls == [
        {
            "actor": actor,
            "organization_id": organization_id,
            "scopes": (DIRECTORY_ORGUNIT_READONLY_SCOPE,),
        }
    ]
    call = factory.client.orgunits_resource.calls[0]
    assert call["method"] == "list"
    assert call["kwargs"]["customerId"] == "google-customer-1"
    assert call["kwargs"]["type"] == "allIncludingParent"
    assert "orgUnitPath" not in call["kwargs"]
    assert factory.client.orgunits_resource.requests[0].execute_kwargs == {"num_retries": 0}
    assert factory.client.closed is True


def test_empty_and_root_only_hierarchies_are_supported(db_session: Session) -> None:
    empty, _, _, organization_id, actor = orgunit_service(
        db_session, {"organizationUnits": []}
    )
    assert empty.list_hierarchy(actor=actor, organization_id=organization_id) == (
        OrganizationalUnitHierarchy(roots=(), total=0)
    )

    root_only, _, _, organization_id, actor = orgunit_service(
        db_session, {"organizationUnits": [ROOT]}
    )
    result = root_only.list_hierarchy(actor=actor, organization_id=organization_id)
    assert result.total == 1
    assert result.roots[0].children == ()


def test_siblings_are_sorted_stably_when_google_order_is_unexpected(db_session: Session) -> None:
    zeta = unit("id:zeta", "Zeta", "/Zeta", "id:root", "/")
    alpha = unit("id:alpha", "Alpha", "/Alpha", "id:root", "/")
    service, _, _, organization_id, actor = orgunit_service(
        db_session, {"organizationUnits": [zeta, ROOT, alpha]}
    )

    result = service.list_hierarchy(actor=actor, organization_id=organization_id)

    assert [child.id for child in result.roots[0].children] == ["id:alpha", "id:zeta"]


@pytest.mark.parametrize(
    "values",
    [
        [ROOT, ROOT],
        [ROOT, ENGINEERING, {**PLATFORM, "orgUnitId": "id:engineering"}],
        [ROOT, unit("id:orphan", "Orphan", "/Orphan", "id:missing", "/")],
        [ROOT, unit("id:self", "Self", "/Self", "id:self", "/Self")],
        [
            ROOT,
            unit("id:a", "A", "/B/A", "id:b", "/B"),
            unit("id:b", "B", "/A/B", "id:a", "/A"),
        ],
        [unit("id:no-root", "No root", "/No root")],
    ],
)
def test_duplicate_missing_parent_and_cyclic_hierarchies_fail_closed(
    db_session: Session, values: list[dict[str, object]]
) -> None:
    service, _, _, organization_id, actor = orgunit_service(
        db_session, {"organizationUnits": values}
    )

    with pytest.raises(GoogleWorkspaceError) as error:
        service.list_hierarchy(actor=actor, organization_id=organization_id)

    assert error.value.code == GoogleWorkspaceErrorCode.GOOGLE_ORGUNIT_HIERARCHY_INVALID


def test_detail_uses_identifier_verified_customer_and_exact_match(db_session: Session) -> None:
    service, factory, _, organization_id, actor = orgunit_service(db_session, ENGINEERING)

    result = service.get_organizational_unit(
        actor=actor,
        organization_id=organization_id,
        org_unit_id="id:engineering",
    )

    assert result.id == "id:engineering"
    assert factory.client.orgunits_resource.calls[0]["kwargs"]["customerId"] == (
        "google-customer-1"
    )
    assert factory.client.orgunits_resource.calls[0]["kwargs"]["orgUnitPath"] == (
        "id:engineering"
    )
    assert factory.client.orgunits_resource.requests[0].execute_kwargs == {"num_retries": 0}


def test_detail_rejects_mismatched_identifier(db_session: Session) -> None:
    service, _, _, organization_id, actor = orgunit_service(db_session, ENGINEERING)

    with pytest.raises(GoogleWorkspaceError) as error:
        service.get_organizational_unit(
            actor=actor,
            organization_id=organization_id,
            org_unit_id="id:different",
        )

    assert error.value.code == GoogleWorkspaceErrorCode.GOOGLE_ORGUNIT_LOOKUP_MISMATCH


@pytest.mark.parametrize(
    ("upstream", "expected"),
    [
        (
            HttpError(
                Response({"status": "403"}),
                b'{"error":{"errors":[{"reason":"insufficientPermissions"}],"message":"private"}}',
            ),
            GoogleWorkspaceErrorCode.MISSING_SCOPE_OR_PERMISSION,
        ),
        (
            HttpError(Response({"status": "429"}), b'{"error":{"message":"private"}}'),
            GoogleWorkspaceErrorCode.GOOGLE_RATE_LIMITED,
        ),
        (
            HttpError(Response({"status": "503"}), b'{"error":{"message":"private"}}'),
            GoogleWorkspaceErrorCode.GOOGLE_SERVICE_UNAVAILABLE,
        ),
        (TimeoutError("private request detail"), GoogleWorkspaceErrorCode.GOOGLE_TIMEOUT),
    ],
)
def test_upstream_errors_are_sanitized(
    db_session: Session, upstream: Exception, expected: GoogleWorkspaceErrorCode
) -> None:
    service, _, _, organization_id, actor = orgunit_service(db_session, upstream)

    with pytest.raises(GoogleWorkspaceError) as error:
        service.list_hierarchy(actor=actor, organization_id=organization_id)

    assert error.value.code == expected
    assert "private" not in str(error.value)


def test_missing_connector_fails_before_orgunit_client(db_session: Session) -> None:
    connector, actor = create_connector(db_session)
    db_session.delete(connector)
    db_session.commit()
    client = FakeDirectoryClient({"organizationUnits": [ROOT]})
    factory = FakeClientFactory(client)
    service = GoogleWorkspaceOrganizationalUnits(
        db_session,
        factory,  # type: ignore[arg-type]
        FakeLookup(),  # type: ignore[arg-type]
    )

    with pytest.raises(GoogleWorkspaceError) as error:
        service.list_hierarchy(actor=actor, organization_id=connector.organization_id)

    assert error.value.code == GoogleWorkspaceErrorCode.CONNECTOR_NOT_CONFIGURED
    assert factory.calls == []


def test_list_endpoint_returns_tree_and_records_safe_audit(
    client: TestClient,
    db_session: Session,
    auth_headers: dict[str, str],
) -> None:
    connector, _ = create_connector(db_session)
    root = OrganizationalUnitTreeNode(
        id="id:root",
        name="Example Workspace",
        description=None,
        path="/",
        parent_id=None,
        parent_path=None,
        children=(
            OrganizationalUnitTreeNode(
                id="id:engineering",
                name="Engineering",
                description="Builders",
                path="/Engineering",
                parent_id="id:root",
                parent_path="/",
                children=(),
            ),
        ),
    )
    service = MagicMock()
    service.list_hierarchy.return_value = OrganizationalUnitHierarchy(roots=(root,), total=2)

    with patch(
        "app.api.v1.router.GoogleWorkspaceOrganizationalUnits.from_settings",
        return_value=service,
    ):
        response = client.post(
            f"/api/v1/organizations/{connector.organization_id}/google-workspace/orgunits/list",
            headers=auth_headers,
        )

    assert response.status_code == 200
    assert response.json()["total"] == 2
    assert response.json()["roots"][0]["children"][0]["read_only"] is True
    service.list_hierarchy.assert_called_once()


def test_detail_endpoint_validates_identifier_and_maps_not_found(
    client: TestClient,
    db_session: Session,
    auth_headers: dict[str, str],
) -> None:
    connector, _ = create_connector(db_session)
    service = MagicMock()
    service.get_organizational_unit.side_effect = GoogleWorkspaceError(
        GoogleWorkspaceErrorCode.GOOGLE_ORGUNIT_NOT_FOUND
    )

    with patch(
        "app.api.v1.router.GoogleWorkspaceOrganizationalUnits.from_settings",
        return_value=service,
    ):
        invalid = client.post(
            f"/api/v1/organizations/{connector.organization_id}/google-workspace/orgunits/get",
            json={"org_unit_id": "/unsafe/path"},
            headers=auth_headers,
        )
        missing = client.post(
            f"/api/v1/organizations/{connector.organization_id}/google-workspace/orgunits/get",
            json={"org_unit_id": "id:missing"},
            headers=auth_headers,
        )

    assert invalid.status_code == 422
    assert missing.status_code == 404
    assert missing.json()["detail"]["code"] == "google_orgunit_not_found"


def test_unrelated_customer_actor_cannot_reach_credentials(
    client: TestClient,
    db_session: Session,
    auth_headers: dict[str, str],
) -> None:
    connector, _ = create_connector(db_session)
    outsider = add_user(db_session, "ou-outsider@example.local")
    assert outsider is not None
    outsider_headers = login_headers(client, "ou-outsider@example.local")

    with patch(
        "app.api.v1.router.GoogleWorkspaceOrganizationalUnits.from_settings"
    ) as service_factory:
        response = client.post(
            f"/api/v1/organizations/{connector.organization_id}/google-workspace/orgunits/list",
            headers=outsider_headers,
        )

    assert response.status_code == 403
    service_factory.assert_not_called()
