from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Literal
from uuid import UUID

from googleapiclient.errors import HttpError
from sqlalchemy.orm import Session

from app.connectors.google_workspace_client import GoogleWorkspaceClientFactory
from app.connectors.google_workspace_credentials import DIRECTORY_GROUP_READONLY_SCOPE
from app.connectors.google_workspace_errors import (
    GoogleWorkspaceError,
    GoogleWorkspaceErrorCode,
    map_google_api_error,
)
from app.models import User
from app.services.google_workspace_groups import GoogleWorkspaceGroupsService
from app.services.google_workspace_user_lookup import (
    GoogleWorkspaceUserLookup,
    GoogleWorkspaceUserLookupResult,
    MatchType,
)

logger = logging.getLogger(__name__)

USER_GROUP_LIST_FIELDS = "groups(id,email,name),nextPageToken"
OWNERSHIP_LIST_FIELDS = "groups(id,email)"
DIRECT_MEMBER_FIELDS = "id,email,role,type,status"
MAX_CANDIDATES_PER_PAGE = 25
VERIFICATION_CALLS_PER_CANDIDATE = 2
MAX_VERIFICATION_CALLS_PER_PAGE = MAX_CANDIDATES_PER_PAGE * VERIFICATION_CALLS_PER_CANDIDATE


@dataclass(frozen=True)
class UserDirectGroupMembership:
    group_id: str
    group_name: str
    group_primary_email: str
    role: Literal["MEMBER", "MANAGER", "OWNER"]
    member_type: Literal["USER"]
    status: str | None


@dataclass(frozen=True)
class UserGroupMembershipListResult:
    user_id: str
    user_primary_email: str
    matched_by: MatchType
    memberships: list[UserDirectGroupMembership]
    next_page_token: str | None
    verification_complete: bool
    candidates_examined: int
    omitted_external_count: int
    omitted_indirect_count: int


@dataclass(frozen=True)
class _CandidateGroup:
    id: str
    name: str
    primary_email: str


class GoogleWorkspaceUserGroupMemberships:
    """Return only verified current-tenant direct memberships for one canonical user."""

    def __init__(
        self,
        client_factory: GoogleWorkspaceClientFactory,
        user_lookup: GoogleWorkspaceUserLookup,
        groups_service: GoogleWorkspaceGroupsService,
    ) -> None:
        self.client_factory = client_factory
        self.user_lookup = user_lookup
        self.groups_service = groups_service

    @classmethod
    def from_settings(cls, db: Session) -> GoogleWorkspaceUserGroupMemberships:
        factory = GoogleWorkspaceClientFactory.from_settings(db)
        lookup = GoogleWorkspaceUserLookup(factory)
        return cls(factory, lookup, GoogleWorkspaceGroupsService(db, factory, lookup))

    def list_memberships(
        self,
        *,
        actor: User,
        organization_id: UUID,
        email: str,
        page_size: int,
        page_token: str | None,
    ) -> UserGroupMembershipListResult:
        customer_id = self.groups_service.verified_customer_id(actor, organization_id)
        user = self.user_lookup.lookup(
            actor=actor,
            organization_id=organization_id,
            email=email,
        )
        if user.customer_id != customer_id:
            raise GoogleWorkspaceError(GoogleWorkspaceErrorCode.GOOGLE_TENANT_MISMATCH)

        client: Any | None = None
        try:
            client = self.client_factory.for_directory_groups(
                actor=actor,
                organization_id=organization_id,
                scopes=(DIRECTORY_GROUP_READONLY_SCOPE,),
            )
            candidates, next_page_token = self._list_candidates(
                client,
                user,
                page_size=page_size,
                page_token=page_token,
            )
            required_calls = len(candidates) * VERIFICATION_CALLS_PER_CANDIDATE
            if required_calls > MAX_VERIFICATION_CALLS_PER_PAGE:
                raise GoogleWorkspaceError(
                    GoogleWorkspaceErrorCode.GOOGLE_OPERATION_BUDGET_EXCEEDED
                )

            memberships: list[UserDirectGroupMembership] = []
            omitted_external = 0
            omitted_indirect = 0
            for candidate in candidates:
                if not self._belongs_to_customer(client, candidate, customer_id):
                    omitted_external += 1
                    continue
                member = self._direct_member(client, candidate.id, user.id)
                if member is None:
                    omitted_indirect += 1
                    continue
                memberships.append(self._membership(candidate, member, user))

            return UserGroupMembershipListResult(
                user_id=user.id,
                user_primary_email=user.primary_email,
                matched_by=user.matched_by,
                memberships=memberships,
                next_page_token=next_page_token,
                verification_complete=True,
                candidates_examined=len(candidates),
                omitted_external_count=omitted_external,
                omitted_indirect_count=omitted_indirect,
            )
        except GoogleWorkspaceError:
            raise
        except HttpError as error:
            raise map_google_api_error(error) from None
        except Exception as error:
            raise map_google_api_error(error) from None
        finally:
            self._close_client(client, organization_id)

    @staticmethod
    def _list_candidates(
        client: Any,
        user: GoogleWorkspaceUserLookupResult,
        *,
        page_size: int,
        page_token: str | None,
    ) -> tuple[list[_CandidateGroup], str | None]:
        arguments: dict[str, Any] = {
            "userKey": user.id,
            "maxResults": page_size,
            "orderBy": "email",
            "sortOrder": "ASCENDING",
            "fields": USER_GROUP_LIST_FIELDS,
        }
        if page_token:
            arguments["pageToken"] = page_token
        try:
            response = client.groups().list(**arguments).execute(num_retries=0)
        except HttpError as error:
            if page_token and error.resp.status == 400:
                raise GoogleWorkspaceError(
                    GoogleWorkspaceErrorCode.GOOGLE_PAGE_TOKEN_INVALID
                ) from None
            raise
        if not isinstance(response, dict):
            raise GoogleWorkspaceError(GoogleWorkspaceErrorCode.GOOGLE_API_ERROR)
        raw_groups = response.get("groups", [])
        if not isinstance(raw_groups, list):
            raise GoogleWorkspaceError(GoogleWorkspaceErrorCode.GOOGLE_API_ERROR)
        candidates = [GoogleWorkspaceUserGroupMemberships._candidate(item) for item in raw_groups]
        token = response.get("nextPageToken")
        return candidates, token if isinstance(token, str) and token else None

    @staticmethod
    def _candidate(value: Any) -> _CandidateGroup:
        if not isinstance(value, dict):
            raise GoogleWorkspaceError(GoogleWorkspaceErrorCode.GOOGLE_API_ERROR)
        group_id = value.get("id")
        name = value.get("name")
        email = value.get("email")
        if not all(isinstance(item, str) and item for item in (group_id, name, email)):
            raise GoogleWorkspaceError(GoogleWorkspaceErrorCode.GOOGLE_API_ERROR)
        return _CandidateGroup(id=group_id, name=name, primary_email=email)

    @staticmethod
    def _belongs_to_customer(client: Any, candidate: _CandidateGroup, customer_id: str) -> bool:
        query_value = GoogleWorkspaceGroupsService._quote_query_value(candidate.primary_email)
        response = (
            client.groups()
            .list(
                customer=customer_id,
                query=f"email={query_value}",
                maxResults=10,
                fields=OWNERSHIP_LIST_FIELDS,
            )
            .execute(num_retries=0)
        )
        if not isinstance(response, dict) or not isinstance(response.get("groups", []), list):
            raise GoogleWorkspaceError(GoogleWorkspaceErrorCode.GOOGLE_API_ERROR)
        return any(
            isinstance(item, dict)
            and item.get("id") == candidate.id
            and isinstance(item.get("email"), str)
            and item["email"].casefold() == candidate.primary_email.casefold()
            for item in response.get("groups", [])
        )

    @staticmethod
    def _direct_member(client: Any, group_id: str, user_id: str) -> dict[str, Any] | None:
        try:
            response = (
                client.members()
                .get(groupKey=group_id, memberKey=user_id, fields=DIRECT_MEMBER_FIELDS)
                .execute(num_retries=0)
            )
        except HttpError as error:
            if error.resp.status == 404:
                return None
            raise
        if not isinstance(response, dict):
            raise GoogleWorkspaceError(GoogleWorkspaceErrorCode.GOOGLE_API_ERROR)
        return response

    @staticmethod
    def _membership(
        group: _CandidateGroup,
        member: dict[str, Any],
        user: GoogleWorkspaceUserLookupResult,
    ) -> UserDirectGroupMembership:
        if member.get("id") != user.id or member.get("type") != "USER":
            raise GoogleWorkspaceError(GoogleWorkspaceErrorCode.GOOGLE_TENANT_MISMATCH)
        role = member.get("role")
        if role not in {"MEMBER", "MANAGER", "OWNER"}:
            raise GoogleWorkspaceError(GoogleWorkspaceErrorCode.GOOGLE_API_ERROR)
        member_email = member.get("email")
        if (
            isinstance(member_email, str)
            and member_email.casefold() != user.primary_email.casefold()
        ):
            raise GoogleWorkspaceError(GoogleWorkspaceErrorCode.GOOGLE_TENANT_MISMATCH)
        status = member.get("status")
        return UserDirectGroupMembership(
            group_id=group.id,
            group_name=group.name,
            group_primary_email=group.primary_email,
            role=role,
            member_type="USER",
            status=status if isinstance(status, str) and status else None,
        )

    @staticmethod
    def _close_client(client: Any | None, organization_id: UUID) -> None:
        if client is None:
            return
        close = getattr(client, "close", None)
        if callable(close):
            try:
                close()
            except Exception:
                logger.warning(
                    "Closing user group membership client failed organization_id=%s",
                    organization_id,
                )
