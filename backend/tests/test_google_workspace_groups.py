from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from googleapiclient.errors import HttpError
from httplib2 import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.connectors.google_workspace_credentials import (
    DIRECTORY_GROUP_MEMBER_SCOPE,
    DIRECTORY_GROUP_READONLY_SCOPE,
)
from app.connectors.google_workspace_errors import (
    GoogleWorkspaceError,
    GoogleWorkspaceErrorCode,
)
from app.models import AuditEvent, GoogleWorkspaceGroupMembershipConfirmation
from app.services.google_workspace_groups import (
    GoogleWorkspaceGroupReconciliationService,
    GoogleWorkspaceGroupSearchResult,
    GoogleWorkspaceGroupsService,
    GroupMembershipMutationAmbiguousError,
)
from app.services.google_workspace_user_lookup import GoogleWorkspaceUserLookupResult
from tests.test_customer_data_scoping import (
    add_membership,
    add_user,
    create_customer,
    create_organization,
    login_headers,
)
from tests.test_google_workspace_connection import create_connector


class FakeRequest:
    def __init__(self, client: FakeDirectoryClient, response: object) -> None:
        self.client = client
        self.response = response

    def execute(self, **kwargs: Any) -> object:
        self.client.calls[-1]["execute_kwargs"] = kwargs
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


class FakeResource:
    def __init__(self, client: FakeDirectoryClient, name: str) -> None:
        self.client = client
        self.name = name

    def __getattr__(self, method: str) -> Any:
        def invoke(**kwargs: Any) -> FakeRequest:
            response = self.client.responses.pop(0)
            self.client.calls.append({"resource": self.name, "method": method, "kwargs": kwargs})
            return FakeRequest(self.client, response)

        return invoke


class FakeDirectoryClient:
    def __init__(self, *responses: object) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []
        self.closed = False

    def groups(self) -> FakeResource:
        return FakeResource(self, "groups")

    def members(self) -> FakeResource:
        return FakeResource(self, "members")

    def close(self) -> None:
        self.closed = True


class FakeClientFactory:
    def __init__(self, clients: list[FakeDirectoryClient]) -> None:
        self.clients = list(clients)
        self.calls: list[dict[str, Any]] = []

    def for_directory_groups(self, **kwargs: Any) -> FakeDirectoryClient:
        self.calls.append(kwargs)
        return self.clients.pop(0)


class FakeUserLookup:
    def __init__(self, identities: dict[str, GoogleWorkspaceUserLookupResult]) -> None:
        self.identities = {key.casefold(): value for key, value in identities.items()}
        self.calls: list[str] = []

    def lookup(self, **kwargs: Any) -> GoogleWorkspaceUserLookupResult:
        email = str(kwargs["email"]).casefold()
        self.calls.append(email)
        identity = self.identities.get(email)
        if identity is None:
            raise GoogleWorkspaceError(GoogleWorkspaceErrorCode.GOOGLE_USER_NOT_FOUND)
        return identity


def identity(
    primary_email: str,
    google_id: str,
    *,
    customer_id: str = "customer-google-1",
    matched_by: str = "primary_email",
) -> GoogleWorkspaceUserLookupResult:
    return GoogleWorkspaceUserLookupResult(
        id=google_id,
        customer_id=customer_id,
        full_name="Example User",
        primary_email=primary_email,
        aliases=[],
        non_editable_aliases=[],
        suspended=False,
        archived=False,
        org_unit_path="/People",
        is_mailbox_setup=True,
        matched_by=matched_by,  # type: ignore[arg-type]
    )


def group_response(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "id": "group-1",
        "email": "team@primary.example",
        "name": "Team",
        "description": "A multi-domain team",
        "aliases": ["team@secondary.example"],
        "nonEditableAliases": [],
        "directMembersCount": "2",
        "adminCreated": True,
    }
    value.update(overrides)
    return value


def member_response(
    email: str = "person@primary.example",
    *,
    google_id: str = "user-1",
    member_type: str = "USER",
    role: str = "MEMBER",
) -> dict[str, str]:
    return {
        "id": google_id,
        "email": email,
        "type": member_type,
        "role": role,
        "status": "ACTIVE",
    }


def groups_service(
    db_session: Session,
    clients: list[FakeDirectoryClient],
    *,
    member: GoogleWorkspaceUserLookupResult | None = None,
) -> tuple[GoogleWorkspaceGroupsService, FakeClientFactory, UUID, Any]:
    connector, actor = create_connector(db_session)
    canonical_member = member or identity("person@primary.example", "user-1")
    lookup = FakeUserLookup(
        {
            "admin@example.com": identity("admin@example.com", "admin-1"),
            "person@primary.example": canonical_member,
            "person.alias@secondary.example": GoogleWorkspaceUserLookupResult(
                **{**canonical_member.__dict__, "matched_by": "alias"}
            ),
        }
    )
    factory = FakeClientFactory(clients)
    service = GoogleWorkspaceGroupsService(db_session, factory, lookup)  # type: ignore[arg-type]
    return service, factory, connector.organization_id, actor


def group_resolution_client(group: dict[str, object] | None = None) -> FakeDirectoryClient:
    group = group or group_response()
    return FakeDirectoryClient(group, {"groups": [group]})


def test_search_uses_verified_customer_read_scope_query_and_pagination(
    db_session: Session,
) -> None:
    search_client = FakeDirectoryClient(
        {"groups": [group_response()], "nextPageToken": "next-page"}
    )
    service, factory, organization_id, actor = groups_service(db_session, [search_client])

    result = service.search_groups(
        actor=actor,
        organization_id=organization_id,
        query="Team",
        page_token="page-1",
        max_results=25,
    )

    assert result.groups[0].primary_email == "team@primary.example"
    assert result.groups[0].direct_members_count == 2
    assert result.next_page_token == "next-page"
    assert factory.calls[0]["scopes"] == (DIRECTORY_GROUP_READONLY_SCOPE,)
    assert search_client.calls[0]["kwargs"]["customer"] == "customer-google-1"
    assert search_client.calls[0]["kwargs"]["query"] == "name:Team*"
    assert search_client.calls[0]["kwargs"]["pageToken"] == "page-1"
    assert search_client.calls[0]["execute_kwargs"] == {"num_retries": 0}
    assert search_client.closed is True


def test_email_search_supports_multi_domain_customer_without_domain_filter(
    db_session: Session,
) -> None:
    client = FakeDirectoryClient({"groups": [group_response()]})
    service, _, organization_id, actor = groups_service(db_session, [client])

    service.search_groups(
        actor=actor,
        organization_id=organization_id,
        query="team@secondary.example",
        page_token=None,
        max_results=50,
    )

    arguments = client.calls[0]["kwargs"]
    assert arguments["customer"] == "customer-google-1"
    assert arguments["query"] == "email:team@secondary.example*"
    assert "domain" not in arguments


def test_group_resolution_rejects_cross_customer_result(db_session: Session) -> None:
    client = FakeDirectoryClient(group_response(), {"groups": []})
    service, _, organization_id, actor = groups_service(db_session, [client])

    with pytest.raises(GoogleWorkspaceError) as exc_info:
        service.get_group(
            actor=actor,
            organization_id=organization_id,
            group_email="team@secondary.example",
        )

    assert exc_info.value.code == GoogleWorkspaceErrorCode.GOOGLE_TENANT_MISMATCH


def test_lists_only_direct_members_with_types_roles_status_and_page_token(
    db_session: Session,
) -> None:
    members_client = FakeDirectoryClient(
        {
            "members": [
                member_response(),
                member_response(
                    "nested@primary.example",
                    google_id="group-2",
                    member_type="GROUP",
                    role="MEMBER",
                ),
            ],
            "nextPageToken": "members-next",
        }
    )
    service, _, organization_id, actor = groups_service(
        db_session, [group_resolution_client(), members_client]
    )

    result = service.list_members(
        actor=actor,
        organization_id=organization_id,
        group_email="team@primary.example",
        page_token="members-page",
        max_results=10,
    )

    assert result.next_page_token == "members-next"
    assert result.members[0].mutation_supported is True
    assert result.members[1].type == "GROUP"
    assert result.members[1].mutation_supported is False
    assert "Nested" in (result.members[1].restriction_reason or "")
    arguments = members_client.calls[0]["kwargs"]
    assert arguments["includeDerivedMembership"] is False
    assert arguments["pageToken"] == "members-page"


def test_add_canonicalizes_alias_uses_member_scope_and_never_retries(
    db_session: Session,
) -> None:
    write_client = FakeDirectoryClient(member_response())
    clients = [
        group_resolution_client(),
        FakeDirectoryClient({"members": []}),
        group_resolution_client(),
        FakeDirectoryClient({"members": []}),
        write_client,
    ]
    service, factory, organization_id, actor = groups_service(db_session, clients)
    preview = service.preview_change(
        actor=actor,
        organization_id=organization_id,
        operation="add",
        group_email="team@secondary.example",
        member_email="person.alias@secondary.example",
    )

    result = service.execute_change(
        actor=actor,
        organization_id=organization_id,
        operation="add",
        confirmation_token=preview.confirmation_token,
    )

    assert preview.group_primary_email == "team@primary.example"
    assert preview.member_primary_email == "person@primary.example"
    assert preview.member_role == "MEMBER"
    assert result.outcome == "added"
    assert factory.calls[-1]["scopes"] == (DIRECTORY_GROUP_MEMBER_SCOPE,)
    assert write_client.calls[0]["method"] == "insert"
    assert write_client.calls[0]["kwargs"]["body"] == {
        "email": "person@primary.example",
        "role": "MEMBER",
    }
    assert write_client.calls[0]["execute_kwargs"] == {"num_retries": 0}
    confirmation = db_session.scalar(select(GoogleWorkspaceGroupMembershipConfirmation))
    assert confirmation is not None
    assert confirmation.status == "succeeded"
    assert confirmation.token_digest != preview.confirmation_token

    with pytest.raises(GoogleWorkspaceError) as replay:
        service.execute_change(
            actor=actor,
            organization_id=organization_id,
            operation="add",
            confirmation_token=preview.confirmation_token,
        )
    assert replay.value.code == GoogleWorkspaceErrorCode.GROUP_CONFIRMATION_USED


def test_add_rejects_cross_tenant_user_before_member_listing(db_session: Session) -> None:
    foreign = identity("person@primary.example", "foreign-user", customer_id="customer-google-2")
    service, factory, organization_id, actor = groups_service(
        db_session, [group_resolution_client()], member=foreign
    )

    with pytest.raises(GoogleWorkspaceError) as exc_info:
        service.preview_change(
            actor=actor,
            organization_id=organization_id,
            operation="add",
            group_email="team@primary.example",
            member_email="person@primary.example",
        )

    assert exc_info.value.code == GoogleWorkspaceErrorCode.GOOGLE_TENANT_MISMATCH
    assert len(factory.calls) == 1


@pytest.mark.parametrize(
    ("member", "expected_code"),
    [
        (member_response(role="OWNER"), GoogleWorkspaceErrorCode.GROUP_OWNER_PROTECTED),
        (
            member_response(
                "nested@primary.example",
                google_id="group-2",
                member_type="GROUP",
            ),
            GoogleWorkspaceErrorCode.GROUP_MEMBER_UNSUPPORTED,
        ),
    ],
)
def test_remove_protects_owner_and_nested_members(
    db_session: Session,
    member: dict[str, str],
    expected_code: GoogleWorkspaceErrorCode,
) -> None:
    identities_member = (
        identity(member["email"], member["id"])
        if member["type"] == "USER"
        else identity("person@primary.example", "user-1")
    )
    service, _, organization_id, actor = groups_service(
        db_session,
        [group_resolution_client(), FakeDirectoryClient({"members": [member]})],
        member=identities_member,
    )
    email = member["email"]
    if member["type"] == "GROUP":
        # No Directory user exists for a nested group address.
        service.user_lookup.identities.pop(email.casefold(), None)  # type: ignore[attr-defined]

    with pytest.raises(GoogleWorkspaceError) as exc_info:
        service.preview_change(
            actor=actor,
            organization_id=organization_id,
            operation="remove",
            group_email="team@primary.example",
            member_email=email,
        )

    assert exc_info.value.code == expected_code


def test_dynamic_group_payload_is_marked_read_only() -> None:
    group = GoogleWorkspaceGroupsService._group_from_response(
        group_response(dynamicGroupMetadata={"queries": []})
    )

    assert group.membership_mutable is False
    assert "Dynamic" in (group.restriction_reason or "")


def test_ambiguous_add_is_consumed_and_reconciled_read_only(db_session: Session) -> None:
    timeout_write = FakeDirectoryClient(TimeoutError("private timeout"))
    clients = [
        group_resolution_client(),
        FakeDirectoryClient({"members": []}),
        group_resolution_client(),
        FakeDirectoryClient({"members": []}),
        timeout_write,
        group_resolution_client(),
        FakeDirectoryClient({"members": [member_response()]}),
    ]
    service, factory, organization_id, actor = groups_service(db_session, clients)
    preview = service.preview_change(
        actor=actor,
        organization_id=organization_id,
        operation="add",
        group_email="team@primary.example",
        member_email="person@primary.example",
    )
    with pytest.raises(GroupMembershipMutationAmbiguousError):
        service.execute_change(
            actor=actor,
            organization_id=organization_id,
            operation="add",
            confirmation_token=preview.confirmation_token,
        )
    reconciled = GoogleWorkspaceGroupReconciliationService(
        db_session, service, poll_delays=(0,)
    ).reconcile_change(
        actor=actor,
        organization_id=organization_id,
        operation="add",
        confirmation_token=preview.confirmation_token,
    )

    assert reconciled.status == "verified"
    assert reconciled.observed_state == "present"
    assert "does not prove" in reconciled.message
    assert sum(call["scopes"] == (DIRECTORY_GROUP_MEMBER_SCOPE,) for call in factory.calls) == 1
    assert factory.calls[-1]["request_timeout_seconds"] <= 5


def test_group_search_query_escapes_names_and_selects_email_field() -> None:
    assert GoogleWorkspaceGroupsService._group_search_query("Valentine's Day") == (
        "name:'Valentine\\'s Day'*"
    )
    assert GoogleWorkspaceGroupsService._group_search_query("team@example.com") == (
        "email:team@example.com*"
    )


@pytest.mark.parametrize(
    ("status_code", "expected_code"),
    [
        (401, GoogleWorkspaceErrorCode.GOOGLE_UNAUTHORIZED),
        (403, GoogleWorkspaceErrorCode.GOOGLE_FORBIDDEN),
        (404, GoogleWorkspaceErrorCode.GOOGLE_GROUP_NOT_FOUND),
        (429, GoogleWorkspaceErrorCode.GOOGLE_RATE_LIMITED),
        (503, GoogleWorkspaceErrorCode.GOOGLE_SERVICE_UNAVAILABLE),
    ],
)
def test_group_reads_map_google_errors_without_leaking_details(
    db_session: Session,
    status_code: int,
    expected_code: GoogleWorkspaceErrorCode,
) -> None:
    upstream = HttpError(
        Response({"status": str(status_code)}), b'{"error":{"message":"private detail"}}'
    )
    service, _, organization_id, actor = groups_service(db_session, [FakeDirectoryClient(upstream)])

    with pytest.raises(GoogleWorkspaceError) as exc_info:
        service.search_groups(
            actor=actor,
            organization_id=organization_id,
            query="",
            page_token=None,
            max_results=50,
        )

    assert exc_info.value.code == expected_code
    assert "private" not in str(exc_info.value)


def test_customer_user_can_read_groups_but_cannot_preview_writes(
    client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
) -> None:
    customer = create_customer(client, auth_headers, "Groups Role Customer")
    organization = create_organization(
        client, auth_headers, customer["id"], "Groups Role Organization"
    )
    customer_user = add_user(db_session, "groups-user@example.test")
    add_membership(db_session, customer_user, customer["id"], "customer_user")
    headers = login_headers(client, customer_user.email)
    service = MagicMock()
    service.search_groups.return_value = GoogleWorkspaceGroupSearchResult(
        groups=[], next_page_token=None
    )

    with patch(
        "app.api.v1.router.GoogleWorkspaceGroupsService.from_settings",
        return_value=service,
    ) as factory:
        read_response = client.post(
            f"/api/v1/organizations/{organization['id']}/google-workspace/groups/search",
            json={"query": "", "max_results": 50},
            headers=headers,
        )
        write_response = client.post(
            f"/api/v1/organizations/{organization['id']}/google-workspace/groups/members/add/preview",
            json={
                "group_email": "team@example.test",
                "member_email": "person@example.test",
            },
            headers=headers,
        )

    assert read_response.status_code == 200
    assert read_response.json() == {"groups": [], "next_page_token": None}
    assert write_response.status_code == 403
    assert factory.call_count == 1
    denied = db_session.scalar(
        select(AuditEvent)
        .where(
            AuditEvent.customer_id == UUID(customer["id"]),
            AuditEvent.action == "google_workspace.group_membership.add_previewed",
        )
        .order_by(AuditEvent.created_at.desc())
    )
    assert denied is not None
    assert denied.outcome == "rejected"
    assert denied.reason == "organization_access_denied"


def test_cross_tenant_group_read_is_denied_before_service_creation(
    client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
) -> None:
    customer = create_customer(client, auth_headers, "Groups Foreign Customer")
    organization = create_organization(
        client, auth_headers, customer["id"], "Groups Foreign Organization"
    )
    other = create_customer(client, auth_headers, "Groups Other Customer")
    foreign_user = add_user(db_session, "groups-foreign@example.test")
    add_membership(db_session, foreign_user, other["id"], "customer_admin")
    headers = login_headers(client, foreign_user.email)

    with patch("app.api.v1.router.GoogleWorkspaceGroupsService.from_settings") as factory:
        response = client.post(
            f"/api/v1/organizations/{organization['id']}/google-workspace/groups/search",
            json={"query": ""},
            headers=headers,
        )

    assert response.status_code == 403
    factory.assert_not_called()
