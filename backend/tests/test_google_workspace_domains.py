from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.connectors.google_workspace_credentials import DIRECTORY_DOMAIN_READONLY_SCOPE
from app.connectors.google_workspace_errors import GoogleWorkspaceError, GoogleWorkspaceErrorCode
from app.services.google_workspace_domains import (
    GoogleWorkspaceDomains,
    WorkspaceDomain,
    WorkspaceDomainAlias,
    WorkspaceDomainInventory,
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


class FakeResource:
    def __init__(self, response: object) -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []
        self.request: FakeRequest | None = None

    def list(self, **kwargs: Any) -> FakeRequest:
        self.calls.append(kwargs)
        self.request = FakeRequest(self.response)
        return self.request


class FakeDirectoryClient:
    def __init__(self, domains: object, aliases: object) -> None:
        self.domains_resource = FakeResource(domains)
        self.aliases_resource = FakeResource(aliases)
        self.closed = False

    def domains(self) -> FakeResource:
        return self.domains_resource

    def domainAliases(self) -> FakeResource:  # noqa: N802 - mirrors Google client
        return self.aliases_resource

    def close(self) -> None:
        self.closed = True


class FakeFactory:
    def __init__(self, client: FakeDirectoryClient) -> None:
        self.client = client
        self.calls: list[dict[str, Any]] = []

    def for_directory_domains(self, **kwargs: Any) -> FakeDirectoryClient:
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


def domain_service(
    db_session: Session,
    domains: object,
    aliases: object,
    *,
    customer_id: str = "google-customer-1",
) -> tuple[GoogleWorkspaceDomains, FakeFactory, FakeLookup, UUID, Any]:
    connector, actor = create_connector(db_session)
    factory = FakeFactory(FakeDirectoryClient(domains, aliases))
    lookup = FakeLookup(customer_id)
    service = GoogleWorkspaceDomains(
        db_session,
        factory,  # type: ignore[arg-type]
        lookup,  # type: ignore[arg-type]
    )
    return service, factory, lookup, connector.organization_id, actor


def test_list_uses_verified_customer_readonly_scope_and_no_retries(
    db_session: Session,
) -> None:
    embedded_alias = {
        "domainAliasName": "alias.example.test",
        "parentDomainName": "example.test",
        "verified": True,
        "creationTime": "1700000002",
    }
    service, factory, lookup, organization_id, actor = domain_service(
        db_session,
        {
            "domains": [
                {
                    "domainName": "example.test",
                    "isPrimary": True,
                    "verified": True,
                    "creationTime": "1700000000",
                    "domainAliases": [embedded_alias],
                },
                {
                    "domainName": "secondary.example.test",
                    "isPrimary": False,
                    "verified": False,
                },
            ]
        },
        {"domainAliases": [embedded_alias]},
    )

    result = service.list_inventory(actor=actor, organization_id=organization_id)

    assert [domain.kind for domain in result.domains] == ["primary", "secondary"]
    assert result.domains[1].verified is False
    assert result.domains[1].creation_time is None
    assert result.aliases == (
        WorkspaceDomainAlias(
            name="alias.example.test",
            parent_domain="example.test",
            verified=True,
            creation_time=1700000002,
        ),
    )
    assert lookup.calls[0]["email"] == "admin@example.com"
    assert factory.calls == [
        {
            "actor": actor,
            "organization_id": organization_id,
            "scopes": (DIRECTORY_DOMAIN_READONLY_SCOPE,),
        }
    ]
    assert factory.client.domains_resource.calls[0]["customer"] == "google-customer-1"
    assert factory.client.aliases_resource.calls[0]["customer"] == "google-customer-1"
    assert factory.client.domains_resource.request.execute_kwargs == {"num_retries": 0}
    assert factory.client.aliases_resource.request.execute_kwargs == {"num_retries": 0}
    assert factory.client.closed is True


def test_empty_inventory_and_missing_optional_metadata_are_preserved(
    db_session: Session,
) -> None:
    empty, _, _, organization_id, actor = domain_service(db_session, {}, {})
    assert empty.list_inventory(actor=actor, organization_id=organization_id) == (
        WorkspaceDomainInventory(domains=(), aliases=())
    )

    unknown, _, _, organization_id, actor = domain_service(
        db_session,
        {"domains": [{"domainName": "unknown.example.test"}]},
        {"domainAliases": []},
    )
    assert unknown.list_inventory(actor=actor, organization_id=organization_id).domains == (
        WorkspaceDomain(
            name="unknown.example.test",
            kind="domain",
            verified=None,
            creation_time=None,
        ),
    )


def test_multiple_aliases_and_deduplication_merge_missing_metadata(
    db_session: Session,
) -> None:
    service, _, _, organization_id, actor = domain_service(
        db_session,
        {
            "domains": [
                {
                    "domainName": "example.test",
                    "isPrimary": True,
                    "domainAliases": [
                        {
                            "domainAliasName": "Alias.Example.test",
                            "parentDomainName": "example.test",
                            "verified": True,
                        }
                    ],
                }
            ]
        },
        {
            "domainAliases": [
                {
                    "domainAliasName": "alias.example.test",
                    "parentDomainName": "example.test",
                    "creationTime": "1700000001",
                },
                {
                    "domainAliasName": "other.example.test",
                    "parentDomainName": "example.test",
                    "verified": False,
                },
            ]
        },
    )

    result = service.list_inventory(actor=actor, organization_id=organization_id)

    assert len(result.aliases) == 2
    assert result.aliases[0].name == "alias.example.test"
    assert result.aliases[0].verified is True
    assert result.aliases[0].creation_time == 1700000001


@pytest.mark.parametrize(
    ("domains", "aliases"),
    [
        ({"domains": "invalid"}, {}),
        ({"domains": [{"domainName": "duplicate.test"}, {"domainName": "DUPLICATE.test"}]}, {}),
        (
            {"domains": [{"domainName": "example.test"}]},
            {
                "domainAliases": [
                    {"domainAliasName": "orphan.test", "parentDomainName": "missing.test"}
                ]
            },
        ),
        ({"domains": [{"domainName": "example.test", "verified": "yes"}]}, {}),
        (
            {
                "domains": [
                    {"domainName": "one.test", "isPrimary": True},
                    {"domainName": "two.test", "isPrimary": True},
                ]
            },
            {},
        ),
        (
            {
                "domains": [
                    {
                        "domainName": "example.test",
                        "domainAliases": [
                            {
                                "domainAliasName": "alias.test",
                                "parentDomainName": "example.test",
                                "verified": True,
                            }
                        ],
                    }
                ]
            },
            {
                "domainAliases": [
                    {
                        "domainAliasName": "alias.test",
                        "parentDomainName": "example.test",
                        "verified": False,
                    }
                ]
            },
        ),
    ],
)
def test_malformed_conflicting_or_cross_domain_responses_fail_closed(
    db_session: Session, domains: object, aliases: object
) -> None:
    service, _, _, organization_id, actor = domain_service(db_session, domains, aliases)

    with pytest.raises(GoogleWorkspaceError) as error:
        service.list_inventory(actor=actor, organization_id=organization_id)

    assert error.value.code == GoogleWorkspaceErrorCode.GOOGLE_API_ERROR


@pytest.mark.parametrize(
    "code",
    [
        GoogleWorkspaceErrorCode.MISSING_SCOPE_OR_PERMISSION,
        GoogleWorkspaceErrorCode.GOOGLE_FORBIDDEN,
        GoogleWorkspaceErrorCode.GOOGLE_RATE_LIMITED,
        GoogleWorkspaceErrorCode.GOOGLE_SERVICE_UNAVAILABLE,
        GoogleWorkspaceErrorCode.GOOGLE_NETWORK_ERROR,
    ],
)
def test_google_failures_are_sanitized_and_client_is_closed(
    db_session: Session, code: GoogleWorkspaceErrorCode
) -> None:
    service, factory, _, organization_id, actor = domain_service(
        db_session, GoogleWorkspaceError(code), {}
    )

    with pytest.raises(GoogleWorkspaceError) as error:
        service.list_inventory(actor=actor, organization_id=organization_id)

    assert error.value.code == code
    assert factory.client.closed is True


def test_missing_connector_fails_before_google_client_creation(db_session: Session) -> None:
    connector, actor = create_connector(db_session)
    organization_id = connector.organization_id
    db_session.delete(connector)
    db_session.commit()
    factory = FakeFactory(FakeDirectoryClient({}, {}))
    service = GoogleWorkspaceDomains(
        db_session,
        factory,  # type: ignore[arg-type]
        FakeLookup(),  # type: ignore[arg-type]
    )

    with pytest.raises(GoogleWorkspaceError) as error:
        service.list_inventory(actor=actor, organization_id=organization_id)

    assert error.value.code == GoogleWorkspaceErrorCode.CONNECTOR_NOT_CONFIGURED
    assert factory.calls == []


def test_endpoint_returns_inventory_and_records_only_aggregate_metadata(
    client: TestClient,
    db_session: Session,
    auth_headers: dict[str, str],
) -> None:
    connector, _ = create_connector(db_session)
    service = MagicMock()
    service.list_inventory.return_value = WorkspaceDomainInventory(
        domains=(WorkspaceDomain("example.test", "primary", True, 1700000000),),
        aliases=(WorkspaceDomainAlias("alias.example.test", "example.test", None, None),),
    )

    with patch("app.api.v1.router.GoogleWorkspaceDomains.from_settings", return_value=service):
        response = client.post(
            f"/api/v1/organizations/{connector.organization_id}/google-workspace/domains/list",
            headers=auth_headers,
        )

    assert response.status_code == 200
    assert response.json() == {
        "domains": [
            {
                "name": "example.test",
                "kind": "primary",
                "verified": True,
                "creation_time": 1700000000,
            }
        ],
        "aliases": [
            {
                "name": "alias.example.test",
                "parent_domain": "example.test",
                "kind": "alias",
                "verified": None,
                "creation_time": None,
            }
        ],
        "domain_count": 1,
        "alias_count": 1,
        "read_only": True,
    }


@pytest.mark.parametrize(
    ("code", "expected_status"),
    [
        (GoogleWorkspaceErrorCode.MISSING_SCOPE_OR_PERMISSION, 403),
        (GoogleWorkspaceErrorCode.GOOGLE_FORBIDDEN, 403),
        (GoogleWorkspaceErrorCode.GOOGLE_RATE_LIMITED, 429),
        (GoogleWorkspaceErrorCode.GOOGLE_SERVICE_UNAVAILABLE, 503),
        (GoogleWorkspaceErrorCode.GOOGLE_NETWORK_ERROR, 503),
    ],
)
def test_endpoint_maps_sanitized_google_failures(
    client: TestClient,
    db_session: Session,
    auth_headers: dict[str, str],
    code: GoogleWorkspaceErrorCode,
    expected_status: int,
) -> None:
    connector, _ = create_connector(db_session)
    service = MagicMock()
    service.list_inventory.side_effect = GoogleWorkspaceError(code)

    with patch("app.api.v1.router.GoogleWorkspaceDomains.from_settings", return_value=service):
        response = client.post(
            f"/api/v1/organizations/{connector.organization_id}/google-workspace/domains/list",
            headers=auth_headers,
        )

    assert response.status_code == expected_status
    assert response.json()["detail"]["code"] == code.value


def test_unrelated_customer_actor_cannot_reach_domain_service(
    client: TestClient,
    db_session: Session,
) -> None:
    connector, _ = create_connector(db_session)
    add_user(db_session, "domain-outsider@example.local")
    outsider_headers = login_headers(client, "domain-outsider@example.local")

    with patch("app.api.v1.router.GoogleWorkspaceDomains.from_settings") as service_factory:
        response = client.post(
            f"/api/v1/organizations/{connector.organization_id}/google-workspace/domains/list",
            headers=outsider_headers,
        )

    assert response.status_code == 403
    service_factory.assert_not_called()
