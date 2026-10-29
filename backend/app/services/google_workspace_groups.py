from __future__ import annotations

import logging
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from googleapiclient.errors import HttpError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.connectors.google_workspace_client import GoogleWorkspaceClientFactory
from app.connectors.google_workspace_credentials import (
    DIRECTORY_GROUP_MEMBER_SCOPE,
    DIRECTORY_GROUP_READONLY_SCOPE,
)
from app.connectors.google_workspace_errors import (
    GoogleWorkspaceError,
    GoogleWorkspaceErrorCode,
    map_google_api_error,
)
from app.models import (
    ConnectorConfig,
    GoogleWorkspaceGroupMembershipConfirmation,
    User,
)
from app.services.google_workspace_mutation_safety import (
    RECONCILIATION_BACKOFF_SECONDS,
    RECONCILIATION_MAX_WAIT_SECONDS,
    BoundedReconciliationWindow,
    aware_utc,
    confirmation_blocks_new_preview,
    confirmation_is_expired,
    confirmation_token_digest,
    consume_confirmation,
    is_ambiguous_mutation_error,
    issue_confirmation,
    mark_confirmation_reconciled,
    set_confirmation_status,
)
from app.services.google_workspace_user_lookup import (
    GoogleWorkspaceUserLookup,
    GoogleWorkspaceUserLookupResult,
)

logger = logging.getLogger(__name__)
GroupMembershipOperation = Literal["add", "remove"]
GROUP_FIELDS = (
    "id,email,name,description,adminCreated,directMembersCount,aliases,nonEditableAliases"
)
GROUP_LIST_FIELDS = f"groups({GROUP_FIELDS}),nextPageToken"
MEMBER_LIST_FIELDS = "members(id,email,role,type,status),nextPageToken"


@dataclass(frozen=True)
class GoogleWorkspaceGroup:
    id: str
    primary_email: str
    name: str
    description: str | None
    aliases: list[str]
    non_editable_aliases: list[str]
    direct_members_count: int | None
    membership_mutable: bool
    restriction_reason: str | None


@dataclass(frozen=True)
class GoogleWorkspaceGroupSearchResult:
    groups: list[GoogleWorkspaceGroup]
    next_page_token: str | None


@dataclass(frozen=True)
class GoogleWorkspaceGroupMember:
    id: str
    email: str | None
    type: Literal["USER", "GROUP", "CUSTOMER", "EXTERNAL", "UNKNOWN"]
    role: Literal["MEMBER", "MANAGER", "OWNER", "UNKNOWN"]
    status: str | None
    direct: bool
    mutation_supported: bool
    restriction_reason: str | None


@dataclass(frozen=True)
class GoogleWorkspaceGroupMemberListResult:
    group: GoogleWorkspaceGroup
    members: list[GoogleWorkspaceGroupMember]
    next_page_token: str | None


@dataclass(frozen=True)
class GroupMembershipChangePreview:
    operation: GroupMembershipOperation
    group_primary_email: str
    member_primary_email: str
    member_role: Literal["MEMBER", "MANAGER", "OWNER"]
    confirmation_token: str
    expires_at: datetime
    effect: str


@dataclass(frozen=True)
class GroupMembershipMutationResult:
    operation: GroupMembershipOperation
    group_primary_email: str
    member_primary_email: str
    outcome: Literal["added", "removed"]
    message: str


@dataclass(frozen=True)
class GroupMembershipReconciliationResult:
    operation: GroupMembershipOperation
    group_primary_email: str
    member_primary_email: str
    status: Literal["verified", "unknown"]
    observed_state: Literal["present", "absent"]
    attempts: int
    correlation_id: str
    message: str


class GroupMembershipMutationAmbiguousError(GoogleWorkspaceError):
    def __init__(self, code: GoogleWorkspaceErrorCode, correlation_id: UUID) -> None:
        self.correlation_id = str(correlation_id)
        super().__init__(code)


class GroupMembershipReconciliationError(GoogleWorkspaceError):
    def __init__(
        self,
        code: GoogleWorkspaceErrorCode,
        correlation_id: UUID,
        attempts: int,
        *,
        retryable: bool = False,
    ) -> None:
        self.correlation_id = str(correlation_id)
        self.attempts = attempts
        super().__init__(code, retryable=retryable)


class GoogleWorkspaceGroupsService:
    """Customer-scoped Directory group discovery and guarded direct-user membership changes."""

    def __init__(
        self,
        db: Session,
        client_factory: GoogleWorkspaceClientFactory,
        user_lookup: GoogleWorkspaceUserLookup,
    ) -> None:
        self.db = db
        self.client_factory = client_factory
        self.user_lookup = user_lookup

    @classmethod
    def from_settings(cls, db: Session) -> GoogleWorkspaceGroupsService:
        factory = GoogleWorkspaceClientFactory.from_settings(db)
        return cls(db, factory, GoogleWorkspaceUserLookup(factory))

    def search_groups(
        self,
        *,
        actor: User,
        organization_id: UUID,
        query: str,
        page_token: str | None,
        max_results: int,
    ) -> GoogleWorkspaceGroupSearchResult:
        customer_id = self._verified_customer_id(actor, organization_id)
        client: Any | None = None
        try:
            client = self._read_client(actor, organization_id)
            arguments: dict[str, Any] = {
                "customer": customer_id,
                "maxResults": max_results,
                "orderBy": "email",
                "sortOrder": "ASCENDING",
                "fields": GROUP_LIST_FIELDS,
            }
            if page_token:
                arguments["pageToken"] = page_token
            if query:
                arguments["query"] = self._group_search_query(query)
            response = client.groups().list(**arguments).execute(num_retries=0)
            return self._group_search_result(response)
        except GoogleWorkspaceError:
            raise
        except Exception as error:
            raise self._map_group_error(error, operation="list") from None
        finally:
            self._close_client(client, organization_id)

    def get_group(
        self,
        *,
        actor: User,
        organization_id: UUID,
        group_email: str,
    ) -> GoogleWorkspaceGroup:
        customer_id = self._verified_customer_id(actor, organization_id)
        return self._resolve_group(actor, organization_id, customer_id, group_email)

    def list_members(
        self,
        *,
        actor: User,
        organization_id: UUID,
        group_email: str,
        page_token: str | None,
        max_results: int,
        request_timeout_seconds: float | None = None,
    ) -> GoogleWorkspaceGroupMemberListResult:
        customer_id = self._verified_customer_id(actor, organization_id)
        group = self._resolve_group(actor, organization_id, customer_id, group_email)
        return self._list_members_for_group(
            actor,
            organization_id,
            group,
            page_token=page_token,
            max_results=max_results,
            request_timeout_seconds=request_timeout_seconds,
        )

    def preview_change(
        self,
        *,
        actor: User,
        organization_id: UUID,
        operation: GroupMembershipOperation,
        group_email: str,
        member_email: str,
    ) -> GroupMembershipChangePreview:
        group, member = self._resolve_change_identities(
            actor, organization_id, group_email, member_email, operation=operation
        )
        current = self._all_direct_members(actor, organization_id, group)
        existing = self._find_member(current, member.id, member.primary_email)
        if operation == "add" and existing is not None:
            raise GoogleWorkspaceError(GoogleWorkspaceErrorCode.GROUP_MEMBER_ALREADY_EXISTS)
        if operation == "remove":
            self._validate_removal(existing)
        grant = issue_confirmation()
        statement = select(GoogleWorkspaceGroupMembershipConfirmation).where(
            GoogleWorkspaceGroupMembershipConfirmation.organization_id == organization_id,
            GoogleWorkspaceGroupMembershipConfirmation.operation == operation,
            GoogleWorkspaceGroupMembershipConfirmation.group_google_id == group.id,
            GoogleWorkspaceGroupMembershipConfirmation.member_google_id == member.id,
        )
        confirmation = self.db.scalar(statement)
        if confirmation is not None and self._confirmation_blocks_new_preview(confirmation):
            raise GoogleWorkspaceError(GoogleWorkspaceErrorCode.GROUP_CONFIRMATION_USED)
        if confirmation is None:
            confirmation = GoogleWorkspaceGroupMembershipConfirmation(
                organization_id=organization_id,
                actor_user_id=actor.id,
                operation=operation,
                group_google_id=group.id,
                group_primary_email=group.primary_email,
                member_google_id=member.id,
                member_primary_email=member.primary_email,
                token_digest=grant.token_digest,
                expires_at=grant.expires_at,
            )
            self.db.add(confirmation)
        else:
            confirmation.actor_user_id = actor.id
            confirmation.group_primary_email = group.primary_email
            confirmation.member_primary_email = member.primary_email
            confirmation.token_digest = grant.token_digest
            confirmation.status = "pending"
            confirmation.expires_at = grant.expires_at
            confirmation.consumed_at = None
        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            confirmation = self.db.scalar(statement)
            if confirmation is None or self._confirmation_blocks_new_preview(confirmation):
                raise GoogleWorkspaceError(
                    GoogleWorkspaceErrorCode.GROUP_CONFIRMATION_USED
                ) from None
            confirmation.actor_user_id = actor.id
            confirmation.group_primary_email = group.primary_email
            confirmation.member_primary_email = member.primary_email
            confirmation.token_digest = grant.token_digest
            confirmation.status = "pending"
            confirmation.expires_at = grant.expires_at
            confirmation.consumed_at = None
            self.db.commit()
        existing_role: Literal["MEMBER", "MANAGER", "OWNER"] = "MEMBER"
        if existing is not None and existing.role in {"MEMBER", "MANAGER", "OWNER"}:
            existing_role = existing.role
        effect = (
            "The existing internal user will be added as a direct MEMBER. No role is changed."
            if operation == "add"
            else f"The user's direct {existing_role} membership will be removed from this group."
        )
        return GroupMembershipChangePreview(
            operation=operation,
            group_primary_email=group.primary_email,
            member_primary_email=member.primary_email,
            member_role=existing_role,
            confirmation_token=grant.token,
            expires_at=grant.expires_at,
            effect=effect,
        )

    def execute_change(
        self,
        *,
        actor: User,
        organization_id: UUID,
        operation: GroupMembershipOperation,
        confirmation_token: str,
    ) -> GroupMembershipMutationResult:
        digest = confirmation_token_digest(confirmation_token)
        confirmation = self.db.scalar(
            select(GoogleWorkspaceGroupMembershipConfirmation).where(
                GoogleWorkspaceGroupMembershipConfirmation.token_digest == digest,
                GoogleWorkspaceGroupMembershipConfirmation.organization_id == organization_id,
                GoogleWorkspaceGroupMembershipConfirmation.operation == operation,
                GoogleWorkspaceGroupMembershipConfirmation.actor_user_id == actor.id,
            )
        )
        if confirmation is None:
            raise GoogleWorkspaceError(GoogleWorkspaceErrorCode.GROUP_CONFIRMATION_INVALID)
        if confirmation.status != "pending":
            raise GoogleWorkspaceError(GoogleWorkspaceErrorCode.GROUP_CONFIRMATION_USED)
        if confirmation_is_expired(confirmation.expires_at):
            confirmation.status = "expired"
            self.db.commit()
            raise GoogleWorkspaceError(GoogleWorkspaceErrorCode.GROUP_CONFIRMATION_EXPIRED)
        group, member = self._resolve_change_identities(
            actor,
            organization_id,
            confirmation.group_primary_email,
            confirmation.member_primary_email,
            operation=operation,
        )
        if (
            group.id != confirmation.group_google_id
            or member.id != confirmation.member_google_id
            or group.primary_email.casefold() != confirmation.group_primary_email.casefold()
            or member.primary_email.casefold() != confirmation.member_primary_email.casefold()
        ):
            confirmation.status = "rejected"
            self.db.commit()
            raise GoogleWorkspaceError(GoogleWorkspaceErrorCode.GROUP_CONFIRMATION_INVALID)
        current = self._all_direct_members(actor, organization_id, group)
        existing = self._find_member(current, member.id, member.primary_email)
        if operation == "add" and existing is not None:
            confirmation.status = "rejected"
            self.db.commit()
            raise GoogleWorkspaceError(GoogleWorkspaceErrorCode.GROUP_MEMBER_ALREADY_EXISTS)
        if operation == "remove":
            try:
                self._validate_removal(existing)
            except GoogleWorkspaceError:
                confirmation.status = "rejected"
                self.db.commit()
                raise
        if not consume_confirmation(
            self.db,
            GoogleWorkspaceGroupMembershipConfirmation,
            confirmation_id=confirmation.id,
            token_digest=digest,
        ):
            raise GoogleWorkspaceError(GoogleWorkspaceErrorCode.GROUP_CONFIRMATION_USED)
        try:
            self._execute_google_change(actor, organization_id, operation, group, member)
        except GoogleWorkspaceError as error:
            if is_ambiguous_mutation_error(error):
                self._set_confirmation_status(confirmation.id, "unknown")
                raise GroupMembershipMutationAmbiguousError(error.code, confirmation.id) from None
            self._set_confirmation_status(confirmation.id, "failed")
            raise
        except Exception as error:
            mapped = self._map_group_error(error, operation=operation)
            if is_ambiguous_mutation_error(mapped):
                self._set_confirmation_status(confirmation.id, "unknown")
                raise GroupMembershipMutationAmbiguousError(mapped.code, confirmation.id) from None
            self._set_confirmation_status(confirmation.id, "failed")
            raise mapped from None
        self._set_confirmation_status(confirmation.id, "succeeded")
        outcome: Literal["added", "removed"] = "added" if operation == "add" else "removed"
        return GroupMembershipMutationResult(
            operation=operation,
            group_primary_email=group.primary_email,
            member_primary_email=member.primary_email,
            outcome=outcome,
            message=(
                f"{member.primary_email} was added to {group.primary_email} as MEMBER."
                if operation == "add"
                else f"{member.primary_email} was removed from {group.primary_email}."
            ),
        )

    def _verified_customer_id(self, actor: User, organization_id: UUID) -> str:
        connector = self.db.scalar(
            select(ConnectorConfig).where(
                ConnectorConfig.organization_id == organization_id,
                ConnectorConfig.connector_type == "google_workspace",
            )
        )
        if connector is None or not connector.admin_subject_email:
            raise GoogleWorkspaceError(GoogleWorkspaceErrorCode.CONNECTOR_NOT_CONFIGURED)
        admin = self.user_lookup.lookup(
            actor=actor,
            organization_id=organization_id,
            email=connector.admin_subject_email,
        )
        return admin.customer_id

    def verified_customer_id(self, actor: User, organization_id: UUID) -> str:
        """Resolve the trusted Google customer through the configured delegated administrator."""
        return self._verified_customer_id(actor, organization_id)

    def _resolve_change_identities(
        self,
        actor: User,
        organization_id: UUID,
        group_email: str,
        member_email: str,
        *,
        operation: GroupMembershipOperation,
    ) -> tuple[GoogleWorkspaceGroup, GoogleWorkspaceUserLookupResult]:
        customer_id = self._verified_customer_id(actor, organization_id)
        group = self._resolve_group(actor, organization_id, customer_id, group_email)
        if not group.membership_mutable:
            raise GoogleWorkspaceError(GoogleWorkspaceErrorCode.GROUP_MEMBERSHIP_UNSUPPORTED)
        try:
            member = self.user_lookup.lookup(
                actor=actor,
                organization_id=organization_id,
                email=member_email,
            )
        except GoogleWorkspaceError as error:
            if (
                operation != "remove"
                or error.code != GoogleWorkspaceErrorCode.GOOGLE_USER_NOT_FOUND
            ):
                raise
            normalized = member_email.casefold()
            listed = self._all_direct_members(actor, organization_id, group)
            if any(
                item.email is not None and item.email.casefold() == normalized for item in listed
            ):
                raise GoogleWorkspaceError(
                    GoogleWorkspaceErrorCode.GROUP_MEMBER_UNSUPPORTED
                ) from None
            raise GoogleWorkspaceError(GoogleWorkspaceErrorCode.GROUP_MEMBER_NOT_FOUND) from None
        if member.customer_id != customer_id:
            raise GoogleWorkspaceError(GoogleWorkspaceErrorCode.GOOGLE_TENANT_MISMATCH)
        return group, member

    def _resolve_group(
        self,
        actor: User,
        organization_id: UUID,
        customer_id: str,
        group_email: str,
    ) -> GoogleWorkspaceGroup:
        client: Any | None = None
        normalized = group_email.strip().casefold()
        try:
            client = self._read_client(actor, organization_id)
            response = (
                client.groups().get(groupKey=normalized, fields=GROUP_FIELDS).execute(num_retries=0)
            )
            group = self._group_from_response(response, searched_email=normalized)
            verification = (
                client.groups()
                .list(
                    customer=customer_id,
                    query=f"email={self._quote_query_value(group.primary_email)}",
                    maxResults=10,
                    fields=GROUP_LIST_FIELDS,
                )
                .execute(num_retries=0)
            )
            verified_groups = self._group_search_result(verification).groups
            if not any(item.id == group.id for item in verified_groups):
                raise GoogleWorkspaceError(GoogleWorkspaceErrorCode.GOOGLE_TENANT_MISMATCH)
            return group
        except GoogleWorkspaceError:
            raise
        except HttpError as error:
            if error.resp.status == 404:
                raise GoogleWorkspaceError(
                    GoogleWorkspaceErrorCode.GOOGLE_GROUP_NOT_FOUND
                ) from None
            raise self._map_group_error(error, operation="get") from None
        except Exception as error:
            raise self._map_group_error(error, operation="get") from None
        finally:
            self._close_client(client, organization_id)

    def _list_members_for_group(
        self,
        actor: User,
        organization_id: UUID,
        group: GoogleWorkspaceGroup,
        *,
        page_token: str | None,
        max_results: int,
        request_timeout_seconds: float | None = None,
    ) -> GoogleWorkspaceGroupMemberListResult:
        client: Any | None = None
        try:
            client = self._read_client(
                actor, organization_id, request_timeout_seconds=request_timeout_seconds
            )
            arguments: dict[str, Any] = {
                "groupKey": group.id,
                "includeDerivedMembership": False,
                "maxResults": max_results,
                "fields": MEMBER_LIST_FIELDS,
            }
            if page_token:
                arguments["pageToken"] = page_token
            response = client.members().list(**arguments).execute(num_retries=0)
            if not isinstance(response, dict):
                raise GoogleWorkspaceError(GoogleWorkspaceErrorCode.GOOGLE_API_ERROR)
            members_value = response.get("members", [])
            if not isinstance(members_value, list):
                raise GoogleWorkspaceError(GoogleWorkspaceErrorCode.GOOGLE_API_ERROR)
            members = [self._member_from_response(item) for item in members_value]
            next_page_token = response.get("nextPageToken")
            return GoogleWorkspaceGroupMemberListResult(
                group=group,
                members=members,
                next_page_token=next_page_token if isinstance(next_page_token, str) else None,
            )
        except GoogleWorkspaceError:
            raise
        except Exception as error:
            raise self._map_group_error(error, operation="list") from None
        finally:
            self._close_client(client, organization_id)

    def _all_direct_members(
        self,
        actor: User,
        organization_id: UUID,
        group: GoogleWorkspaceGroup,
        *,
        request_timeout_seconds: float | None = None,
    ) -> list[GoogleWorkspaceGroupMember]:
        members: list[GoogleWorkspaceGroupMember] = []
        page_token: str | None = None
        for _ in range(100):
            page = self._list_members_for_group(
                actor,
                organization_id,
                group,
                page_token=page_token,
                max_results=200,
                request_timeout_seconds=request_timeout_seconds,
            )
            members.extend(page.members)
            page_token = page.next_page_token
            if page_token is None:
                return members
        raise GoogleWorkspaceError(GoogleWorkspaceErrorCode.GOOGLE_API_ERROR)

    def _execute_google_change(
        self,
        actor: User,
        organization_id: UUID,
        operation: GroupMembershipOperation,
        group: GoogleWorkspaceGroup,
        member: GoogleWorkspaceUserLookupResult,
    ) -> None:
        client: Any | None = None
        try:
            client = self.client_factory.for_directory_groups(
                actor=actor,
                organization_id=organization_id,
                scopes=(DIRECTORY_GROUP_MEMBER_SCOPE,),
            )
            if operation == "add":
                (
                    client.members()
                    .insert(
                        groupKey=group.id,
                        body={"email": member.primary_email, "role": "MEMBER"},
                        fields="id,email,role,type,status",
                    )
                    .execute(num_retries=0)
                )
            else:
                (
                    client.members()
                    .delete(groupKey=group.id, memberKey=member.id)
                    .execute(num_retries=0)
                )
        except GoogleWorkspaceError:
            raise
        except Exception as error:
            raise self._map_group_error(error, operation=operation) from None
        finally:
            self._close_client(client, organization_id)

    def _read_client(
        self,
        actor: User,
        organization_id: UUID,
        *,
        request_timeout_seconds: float | None = None,
    ) -> Any:
        return self.client_factory.for_directory_groups(
            actor=actor,
            organization_id=organization_id,
            scopes=(DIRECTORY_GROUP_READONLY_SCOPE,),
            request_timeout_seconds=request_timeout_seconds,
        )

    @staticmethod
    def _group_search_result(response: Any) -> GoogleWorkspaceGroupSearchResult:
        if not isinstance(response, dict):
            raise GoogleWorkspaceError(GoogleWorkspaceErrorCode.GOOGLE_API_ERROR)
        raw_groups = response.get("groups", [])
        if not isinstance(raw_groups, list):
            raise GoogleWorkspaceError(GoogleWorkspaceErrorCode.GOOGLE_API_ERROR)
        groups = [GoogleWorkspaceGroupsService._group_from_response(item) for item in raw_groups]
        token = response.get("nextPageToken")
        return GoogleWorkspaceGroupSearchResult(
            groups=groups,
            next_page_token=token if isinstance(token, str) else None,
        )

    @staticmethod
    def _group_from_response(
        value: Any, *, searched_email: str | None = None
    ) -> GoogleWorkspaceGroup:
        if not isinstance(value, dict):
            raise GoogleWorkspaceError(GoogleWorkspaceErrorCode.GOOGLE_API_ERROR)
        google_id = value.get("id")
        email = value.get("email")
        name = value.get("name")
        if not all(isinstance(item, str) and item for item in (google_id, email, name)):
            raise GoogleWorkspaceError(GoogleWorkspaceErrorCode.GOOGLE_API_ERROR)
        aliases = GoogleWorkspaceGroupsService._string_list(value.get("aliases"))
        non_editable_aliases = GoogleWorkspaceGroupsService._string_list(
            value.get("nonEditableAliases")
        )
        if searched_email is not None and searched_email not in {
            email.casefold(),
            *(alias.casefold() for alias in aliases),
            *(alias.casefold() for alias in non_editable_aliases),
        }:
            raise GoogleWorkspaceError(GoogleWorkspaceErrorCode.GOOGLE_GROUP_LOOKUP_MISMATCH)
        description = value.get("description")
        count_value = value.get("directMembersCount")
        try:
            count = int(count_value) if count_value is not None else None
        except (TypeError, ValueError):
            count = None
        unsupported = bool(value.get("dynamicGroupMetadata")) or any(
            str(item).casefold() == "dynamic"
            for item in value.get("groupTypes", [])
            if isinstance(value.get("groupTypes"), list)
        )
        return GoogleWorkspaceGroup(
            id=google_id,
            primary_email=email,
            name=name,
            description=description if isinstance(description, str) and description else None,
            aliases=aliases,
            non_editable_aliases=non_editable_aliases,
            direct_members_count=count,
            membership_mutable=not unsupported,
            restriction_reason=(
                "Dynamic or special group membership must be managed in Google Admin."
                if unsupported
                else None
            ),
        )

    @staticmethod
    def _member_from_response(value: Any) -> GoogleWorkspaceGroupMember:
        if not isinstance(value, dict) or not isinstance(value.get("id"), str):
            raise GoogleWorkspaceError(GoogleWorkspaceErrorCode.GOOGLE_API_ERROR)
        raw_type = value.get("type")
        member_type: Literal["USER", "GROUP", "CUSTOMER", "EXTERNAL", "UNKNOWN"] = (
            raw_type if raw_type in {"USER", "GROUP", "CUSTOMER", "EXTERNAL"} else "UNKNOWN"
        )
        raw_role = value.get("role")
        role: Literal["MEMBER", "MANAGER", "OWNER", "UNKNOWN"] = (
            raw_role if raw_role in {"MEMBER", "MANAGER", "OWNER"} else "UNKNOWN"
        )
        email = value.get("email")
        status = value.get("status")
        supported = member_type == "USER" and role != "OWNER"
        reason = None
        if member_type == "GROUP":
            reason = "Nested group memberships are visible but must be managed separately."
        elif member_type in {"EXTERNAL", "CUSTOMER", "UNKNOWN"}:
            reason = "This member type is read-only in WGASuite."
        elif role == "OWNER":
            reason = "Owner memberships are protected from removal in WGASuite."
        return GoogleWorkspaceGroupMember(
            id=value["id"],
            email=email if isinstance(email, str) else None,
            type=member_type,
            role=role,
            status=status if isinstance(status, str) else None,
            direct=True,
            mutation_supported=supported,
            restriction_reason=reason,
        )

    @staticmethod
    def _find_member(
        members: list[GoogleWorkspaceGroupMember], google_id: str, primary_email: str
    ) -> GoogleWorkspaceGroupMember | None:
        email = primary_email.casefold()
        return next(
            (
                item
                for item in members
                if item.id == google_id
                or (item.email is not None and item.email.casefold() == email)
            ),
            None,
        )

    @staticmethod
    def _validate_removal(member: GoogleWorkspaceGroupMember | None) -> None:
        if member is None:
            raise GoogleWorkspaceError(GoogleWorkspaceErrorCode.GROUP_MEMBER_NOT_FOUND)
        if member.role == "OWNER":
            raise GoogleWorkspaceError(GoogleWorkspaceErrorCode.GROUP_OWNER_PROTECTED)
        if member.type != "USER":
            raise GoogleWorkspaceError(GoogleWorkspaceErrorCode.GROUP_MEMBER_UNSUPPORTED)

    @staticmethod
    def _group_search_query(query: str) -> str:
        value = GoogleWorkspaceGroupsService._quote_query_value(query)
        field = "email" if "@" in query else "name"
        return f"{field}:{value}*"

    @staticmethod
    def _quote_query_value(value: str) -> str:
        escaped = value.replace("\\", "\\\\").replace("'", "\\'")
        return f"'{escaped}'" if any(character.isspace() for character in value) else escaped

    @staticmethod
    def _string_list(value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        return [item for item in value if isinstance(item, str)]

    @staticmethod
    def _aware(value: datetime) -> datetime:
        return aware_utc(value)

    @staticmethod
    def _confirmation_blocks_new_preview(
        confirmation: GoogleWorkspaceGroupMembershipConfirmation,
    ) -> bool:
        return confirmation_blocks_new_preview(
            confirmation.status, confirmation.expires_at
        )

    def _set_confirmation_status(self, confirmation_id: UUID, status: str) -> None:
        set_confirmation_status(
            self.db,
            GoogleWorkspaceGroupMembershipConfirmation,
            confirmation_id,
            status,  # type: ignore[arg-type]
        )

    @staticmethod
    def _map_group_error(
        error: Exception, *, operation: Literal["list", "get", "add", "remove"]
    ) -> GoogleWorkspaceError:
        mapped = map_google_api_error(error)
        if isinstance(error, HttpError):
            if error.resp.status == 409 and operation == "add":
                return GoogleWorkspaceError(GoogleWorkspaceErrorCode.GROUP_MEMBER_ALREADY_EXISTS)
            if error.resp.status == 404:
                code = (
                    GoogleWorkspaceErrorCode.GROUP_MEMBER_NOT_FOUND
                    if operation == "remove"
                    else GoogleWorkspaceErrorCode.GOOGLE_GROUP_NOT_FOUND
                )
                return GoogleWorkspaceError(code)
            if error.resp.status == 400 and operation in {"add", "remove"}:
                return GoogleWorkspaceError(GoogleWorkspaceErrorCode.GROUP_MEMBERSHIP_UNSUPPORTED)
        return mapped

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
                    "Closing Directory groups client failed organization_id=%s",
                    organization_id,
                )


class GoogleWorkspaceGroupReconciliationService:
    """Observe an ambiguous group membership change without resubmitting the write."""

    def __init__(
        self,
        db: Session,
        groups_service: GoogleWorkspaceGroupsService,
        *,
        poll_delays: Sequence[float] = RECONCILIATION_BACKOFF_SECONDS,
        max_wait_seconds: float = RECONCILIATION_MAX_WAIT_SECONDS,
        sleeper: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        if not poll_delays or poll_delays[0] != 0:
            raise ValueError("reconciliation polling must start without a delay")
        self.db = db
        self.groups_service = groups_service
        self.poll_delays = tuple(poll_delays)
        self.max_wait_seconds = max_wait_seconds
        self.sleeper = sleeper
        self.monotonic = monotonic

    @classmethod
    def from_settings(cls, db: Session) -> GoogleWorkspaceGroupReconciliationService:
        return cls(db, GoogleWorkspaceGroupsService.from_settings(db))

    def reconcile_change(
        self,
        *,
        actor: User,
        organization_id: UUID,
        operation: GroupMembershipOperation,
        confirmation_token: str,
    ) -> GroupMembershipReconciliationResult:
        confirmation = self.db.scalar(
            select(GoogleWorkspaceGroupMembershipConfirmation).where(
                GoogleWorkspaceGroupMembershipConfirmation.token_digest
                == confirmation_token_digest(confirmation_token),
                GoogleWorkspaceGroupMembershipConfirmation.organization_id == organization_id,
                GoogleWorkspaceGroupMembershipConfirmation.operation == operation,
                GoogleWorkspaceGroupMembershipConfirmation.actor_user_id == actor.id,
            )
        )
        if confirmation is None:
            raise GoogleWorkspaceError(GoogleWorkspaceErrorCode.GROUP_RECONCILIATION_NOT_AVAILABLE)
        if confirmation_is_expired(confirmation.expires_at):
            raise GroupMembershipReconciliationError(
                GoogleWorkspaceErrorCode.GROUP_RECONCILIATION_EXPIRED,
                confirmation.id,
                0,
            )
        if confirmation.status == "reconciled":
            return self._result(confirmation, status="verified", attempts=0)
        if confirmation.status != "unknown":
            raise GroupMembershipReconciliationError(
                GoogleWorkspaceErrorCode.GROUP_RECONCILIATION_NOT_AVAILABLE,
                confirmation.id,
                0,
            )
        group, member = self.groups_service._resolve_change_identities(
            actor,
            organization_id,
            confirmation.group_primary_email,
            confirmation.member_primary_email,
            operation=operation,
        )
        if group.id != confirmation.group_google_id or member.id != confirmation.member_google_id:
            raise GroupMembershipReconciliationError(
                GoogleWorkspaceErrorCode.GROUP_CONFIRMATION_INVALID,
                confirmation.id,
                0,
            )
        attempts = 0
        observed: Literal["present", "absent"] = "absent" if operation == "add" else "present"
        window = BoundedReconciliationWindow(
            poll_delays=self.poll_delays,
            max_wait_seconds=self.max_wait_seconds,
            sleeper=self.sleeper,
            monotonic=self.monotonic,
        )
        for attempt in window.attempts():
            attempts = attempt.number
            try:
                members = self.groups_service._all_direct_members(
                    actor,
                    organization_id,
                    group,
                    request_timeout_seconds=attempt.request_timeout_seconds,
                )
            except GoogleWorkspaceError as error:
                if error.retryable and attempts < len(self.poll_delays):
                    continue
                raise GroupMembershipReconciliationError(
                    error.code,
                    confirmation.id,
                    attempts,
                    retryable=error.retryable,
                ) from None
            existing = self.groups_service._find_member(
                members, confirmation.member_google_id, confirmation.member_primary_email
            )
            observed = "present" if existing is not None else "absent"
            verified = (operation == "add" and existing is not None) or (
                operation == "remove" and existing is None
            )
            if verified:
                if not mark_confirmation_reconciled(
                    self.db,
                    GoogleWorkspaceGroupMembershipConfirmation,
                    confirmation.id,
                ):
                    self.db.refresh(confirmation)
                    if confirmation.status != "reconciled":
                        raise GroupMembershipReconciliationError(
                            GoogleWorkspaceErrorCode.GROUP_RECONCILIATION_NOT_AVAILABLE,
                            confirmation.id,
                            attempts,
                        )
                return self._result(confirmation, status="verified", attempts=attempts)
        return self._result(
            confirmation,
            status="unknown",
            attempts=attempts,
            observed_state=observed,
        )

    @staticmethod
    def _result(
        confirmation: GoogleWorkspaceGroupMembershipConfirmation,
        *,
        status: Literal["verified", "unknown"],
        attempts: int,
        observed_state: Literal["present", "absent"] | None = None,
    ) -> GroupMembershipReconciliationResult:
        desired = "present" if confirmation.operation == "add" else "absent"
        observed = observed_state or desired
        message = (
            "The requested membership state is now visible in Google. This verifies the current "
            "state but does not prove which request caused it."
            if status == "verified"
            else "The desired membership state was not observed within the bounded check. The "
            "original change was not resubmitted; refresh before taking another action."
        )
        return GroupMembershipReconciliationResult(
            operation=confirmation.operation,  # type: ignore[arg-type]
            group_primary_email=confirmation.group_primary_email,
            member_primary_email=confirmation.member_primary_email,
            status=status,
            observed_state=observed,
            attempts=attempts,
            correlation_id=str(confirmation.id),
            message=message,
        )
