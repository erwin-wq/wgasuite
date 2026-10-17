from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from googleapiclient.errors import HttpError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.connectors.google_workspace_client import GoogleWorkspaceClientFactory
from app.connectors.google_workspace_credentials import DIRECTORY_USER_READONLY_SCOPE
from app.connectors.google_workspace_errors import (
    GoogleWorkspaceError,
    GoogleWorkspaceErrorCode,
    map_google_api_error,
)
from app.models import ConnectorConfig, User
from app.services.google_workspace_user_lookup import GoogleWorkspaceUserLookup

logger = logging.getLogger(__name__)

UserDirectorySearchField = Literal["all", "email", "given_name", "family_name", "full_name"]
UserDirectorySuspendedFilter = Literal["all", "active", "suspended"]
UserDirectoryAdminFilter = Literal["all", "super_admin", "delegated_admin"]
UserDirectoryArchivedFilter = Literal["all", "archived", "not_archived"]
UserDirectoryOrder = Literal["email", "given_name", "family_name"]
UserDirectorySortDirection = Literal["ascending", "descending"]

USER_DIRECTORY_FIELDS = (
    "users(id,primaryEmail,customerId,name(fullName,givenName,familyName),orgUnitPath,"
    "suspended,archived,isAdmin,isDelegatedAdmin,creationTime,lastLoginTime),nextPageToken"
)
ORDER_BY_VALUES: dict[UserDirectoryOrder, str] = {
    "email": "email",
    "given_name": "givenName",
    "family_name": "familyName",
}
SORT_DIRECTION_VALUES: dict[UserDirectorySortDirection, str] = {
    "ascending": "ASCENDING",
    "descending": "DESCENDING",
}


@dataclass(frozen=True)
class GoogleWorkspaceDirectoryUser:
    id: str
    full_name: str | None
    given_name: str | None
    family_name: str | None
    primary_email: str
    org_unit_path: str | None
    suspended: bool | None
    archived: bool | None
    is_super_admin: bool | None
    is_delegated_admin: bool | None
    creation_time: datetime | None
    last_login_time: datetime | None


@dataclass(frozen=True)
class GoogleWorkspaceUserDirectoryResult:
    users: list[GoogleWorkspaceDirectoryUser]
    next_page_token: str | None


class GoogleWorkspaceUserDirectory:
    """List a tenant's Directory users without persisting profile data."""

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
    def from_settings(cls, db: Session) -> GoogleWorkspaceUserDirectory:
        factory = GoogleWorkspaceClientFactory.from_settings(db)
        return cls(db, factory, GoogleWorkspaceUserLookup(factory))

    def list_users(
        self,
        *,
        actor: User,
        organization_id: UUID,
        search: str,
        search_field: UserDirectorySearchField,
        org_unit_path: str | None,
        suspended: UserDirectorySuspendedFilter,
        admin_status: UserDirectoryAdminFilter,
        archived: UserDirectoryArchivedFilter,
        order_by: UserDirectoryOrder,
        sort_direction: UserDirectorySortDirection,
        page_size: int,
        page_token: str | None,
    ) -> GoogleWorkspaceUserDirectoryResult:
        customer_id = self._verified_customer_id(actor, organization_id)
        client: Any | None = None
        try:
            client = self.client_factory.for_organization(
                actor=actor,
                organization_id=organization_id,
                service="admin",
                version="directory_v1",
                scopes=[DIRECTORY_USER_READONLY_SCOPE],
            )
            arguments: dict[str, Any] = {
                "customer": customer_id,
                "projection": "basic",
                "viewType": "admin_view",
                "maxResults": page_size,
                "orderBy": ORDER_BY_VALUES[order_by],
                "sortOrder": SORT_DIRECTION_VALUES[sort_direction],
                "fields": USER_DIRECTORY_FIELDS,
            }
            query = self.build_query(
                search=search,
                search_field=search_field,
                org_unit_path=org_unit_path,
                suspended=suspended,
                admin_status=admin_status,
                archived=archived,
            )
            if query:
                arguments["query"] = query
            if page_token:
                arguments["pageToken"] = page_token
            response = client.users().list(**arguments).execute(num_retries=0)
            return self._to_result(response, customer_id)
        except GoogleWorkspaceError:
            raise
        except HttpError as error:
            if page_token and error.resp.status == 400:
                raise GoogleWorkspaceError(
                    GoogleWorkspaceErrorCode.GOOGLE_PAGE_TOKEN_INVALID
                ) from None
            raise map_google_api_error(error) from None
        except Exception as error:
            raise map_google_api_error(error) from None
        finally:
            self._close_client(client, organization_id)

    def _verified_customer_id(self, actor: User, organization_id: UUID) -> str:
        connector = self.db.scalar(
            select(ConnectorConfig).where(
                ConnectorConfig.organization_id == organization_id,
                ConnectorConfig.connector_type == "google_workspace",
            )
        )
        if connector is None or not connector.admin_subject_email:
            raise GoogleWorkspaceError(GoogleWorkspaceErrorCode.CONNECTOR_NOT_CONFIGURED)
        administrator = self.user_lookup.lookup(
            actor=actor,
            organization_id=organization_id,
            email=connector.admin_subject_email,
        )
        return administrator.customer_id

    @staticmethod
    def build_query(
        *,
        search: str,
        search_field: UserDirectorySearchField,
        org_unit_path: str | None,
        suspended: UserDirectorySuspendedFilter,
        admin_status: UserDirectoryAdminFilter,
        archived: UserDirectoryArchivedFilter,
    ) -> str:
        clauses: list[str] = []
        if search:
            value = GoogleWorkspaceUserDirectory._format_query_value(search)
            if search_field == "all":
                clauses.append(value)
            elif search_field == "full_name":
                clauses.append(f"name:{value}")
            else:
                field = {
                    "email": "email",
                    "given_name": "givenName",
                    "family_name": "familyName",
                }[search_field]
                suffix = "" if any(character.isspace() for character in search) else "*"
                clauses.append(f"{field}:{value}{suffix}")
        if org_unit_path:
            clauses.append(
                f"orgUnitPath={GoogleWorkspaceUserDirectory._quote_query_value(org_unit_path)}"
            )
        if suspended == "active":
            clauses.append("isSuspended=false")
        elif suspended == "suspended":
            clauses.append("isSuspended=true")
        if admin_status == "super_admin":
            clauses.append("isAdmin=true")
        elif admin_status == "delegated_admin":
            clauses.append("isDelegatedAdmin=true")
        if archived == "archived":
            clauses.append("isArchived=true")
        elif archived == "not_archived":
            clauses.append("isArchived=false")
        return " ".join(clauses)

    @staticmethod
    def _quote_query_value(value: str) -> str:
        escaped = value.replace("\\", "\\\\").replace("'", "\\'")
        return f"'{escaped}'"

    @staticmethod
    def _format_query_value(value: str) -> str:
        if any(character.isspace() for character in value):
            return GoogleWorkspaceUserDirectory._quote_query_value(value)
        return value.replace("'", "\\'")

    @staticmethod
    def _to_result(response: Any, customer_id: str) -> GoogleWorkspaceUserDirectoryResult:
        if not isinstance(response, dict):
            raise GoogleWorkspaceError(GoogleWorkspaceErrorCode.GOOGLE_API_ERROR)
        raw_users = response.get("users", [])
        if not isinstance(raw_users, list):
            raise GoogleWorkspaceError(GoogleWorkspaceErrorCode.GOOGLE_API_ERROR)
        users = [GoogleWorkspaceUserDirectory._to_user(item, customer_id) for item in raw_users]
        token = response.get("nextPageToken")
        return GoogleWorkspaceUserDirectoryResult(
            users=users,
            next_page_token=token if isinstance(token, str) and token else None,
        )

    @staticmethod
    def _to_user(value: Any, customer_id: str) -> GoogleWorkspaceDirectoryUser:
        if not isinstance(value, dict):
            raise GoogleWorkspaceError(GoogleWorkspaceErrorCode.GOOGLE_API_ERROR)
        google_id = value.get("id")
        primary_email = value.get("primaryEmail")
        returned_customer_id = value.get("customerId")
        if not isinstance(google_id, str) or not isinstance(primary_email, str):
            raise GoogleWorkspaceError(GoogleWorkspaceErrorCode.GOOGLE_API_ERROR)
        if not isinstance(returned_customer_id, str) or returned_customer_id != customer_id:
            raise GoogleWorkspaceError(GoogleWorkspaceErrorCode.GOOGLE_TENANT_MISMATCH)
        name = value.get("name")
        name_values = name if isinstance(name, dict) else {}
        return GoogleWorkspaceDirectoryUser(
            id=google_id,
            full_name=GoogleWorkspaceUserDirectory._optional_string(name_values.get("fullName")),
            given_name=GoogleWorkspaceUserDirectory._optional_string(name_values.get("givenName")),
            family_name=GoogleWorkspaceUserDirectory._optional_string(
                name_values.get("familyName")
            ),
            primary_email=primary_email,
            org_unit_path=GoogleWorkspaceUserDirectory._optional_string(value.get("orgUnitPath")),
            suspended=GoogleWorkspaceUserDirectory._optional_bool(value.get("suspended")),
            archived=GoogleWorkspaceUserDirectory._optional_bool(value.get("archived")),
            is_super_admin=GoogleWorkspaceUserDirectory._optional_bool(value.get("isAdmin")),
            is_delegated_admin=GoogleWorkspaceUserDirectory._optional_bool(
                value.get("isDelegatedAdmin")
            ),
            creation_time=GoogleWorkspaceUserDirectory._optional_datetime(
                value.get("creationTime")
            ),
            last_login_time=GoogleWorkspaceUserDirectory._optional_datetime(
                value.get("lastLoginTime")
            ),
        )

    @staticmethod
    def _optional_string(value: Any) -> str | None:
        return value if isinstance(value, str) and value.strip() else None

    @staticmethod
    def _optional_bool(value: Any) -> bool | None:
        return value if isinstance(value, bool) else None

    @staticmethod
    def _optional_datetime(value: Any) -> datetime | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise GoogleWorkspaceError(GoogleWorkspaceErrorCode.GOOGLE_API_ERROR)
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            raise GoogleWorkspaceError(GoogleWorkspaceErrorCode.GOOGLE_API_ERROR) from None

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
                    "Closing Google user directory client failed organization_id=%s",
                    organization_id,
                )
