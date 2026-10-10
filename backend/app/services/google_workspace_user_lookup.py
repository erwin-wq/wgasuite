from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Literal
from uuid import UUID

from googleapiclient.errors import HttpError
from sqlalchemy.orm import Session

from app.connectors.google_workspace_client import GoogleWorkspaceClientFactory
from app.connectors.google_workspace_errors import (
    GoogleWorkspaceError,
    GoogleWorkspaceErrorCode,
    map_google_api_error,
)
from app.models import User
from app.services.google_workspace_connection import DIRECTORY_USER_READONLY_SCOPE

logger = logging.getLogger(__name__)

USER_LOOKUP_FIELDS = (
    "id,primaryEmail,customerId,name(fullName),aliases,nonEditableAliases,suspended,archived,"
    "orgUnitPath,isMailboxSetup"
)
MatchType = Literal["primary_email", "alias", "non_editable_alias"]


@dataclass(frozen=True)
class GoogleWorkspaceUserLookupResult:
    id: str
    customer_id: str
    full_name: str | None
    primary_email: str
    aliases: list[str]
    non_editable_aliases: list[str]
    suspended: bool
    archived: bool | None
    org_unit_path: str | None
    is_mailbox_setup: bool | None
    matched_by: MatchType


class GoogleWorkspaceUserLookup:
    """Resolve one exact Directory user without persisting profile data."""

    def __init__(self, client_factory: GoogleWorkspaceClientFactory) -> None:
        self.client_factory = client_factory

    @classmethod
    def from_settings(cls, db: Session) -> GoogleWorkspaceUserLookup:
        return cls(GoogleWorkspaceClientFactory.from_settings(db))

    def lookup(
        self,
        *,
        actor: User,
        organization_id: UUID,
        email: str,
    ) -> GoogleWorkspaceUserLookupResult:
        normalized_email = email.strip().casefold()
        google_client: Any | None = None
        try:
            google_client = self.client_factory.for_organization(
                actor=actor,
                organization_id=organization_id,
                service="admin",
                version="directory_v1",
                scopes=[DIRECTORY_USER_READONLY_SCOPE],
            )
            response = (
                google_client.users()
                .get(
                    userKey=email,
                    projection="basic",
                    viewType="admin_view",
                    fields=USER_LOOKUP_FIELDS,
                )
                .execute(num_retries=0)
            )
            return self._to_result(response, normalized_email)
        except GoogleWorkspaceError:
            raise
        except HttpError as error:
            if error.resp.status == 404:
                raise GoogleWorkspaceError(
                    GoogleWorkspaceErrorCode.GOOGLE_USER_NOT_FOUND
                ) from None
            raise map_google_api_error(error) from None
        except Exception as error:
            raise map_google_api_error(error) from None
        finally:
            if google_client is not None:
                close = getattr(google_client, "close", None)
                if callable(close):
                    try:
                        close()
                    except Exception:
                        logger.warning(
                            "Closing Google user lookup client failed organization_id=%s",
                            organization_id,
                        )

    @staticmethod
    def _to_result(response: Any, searched_email: str) -> GoogleWorkspaceUserLookupResult:
        if not isinstance(response, dict):
            raise GoogleWorkspaceError(GoogleWorkspaceErrorCode.GOOGLE_API_ERROR)

        google_user_id = response.get("id")
        primary_email = response.get("primaryEmail")
        customer_id = response.get("customerId")
        if (
            not isinstance(google_user_id, str)
            or not isinstance(primary_email, str)
            or not isinstance(customer_id, str)
        ):
            raise GoogleWorkspaceError(GoogleWorkspaceErrorCode.GOOGLE_API_ERROR)

        aliases = GoogleWorkspaceUserLookup._string_list(response.get("aliases"))
        non_editable_aliases = GoogleWorkspaceUserLookup._string_list(
            response.get("nonEditableAliases")
        )
        matched_by = GoogleWorkspaceUserLookup._match_type(
            searched_email,
            primary_email,
            aliases,
            non_editable_aliases,
        )

        name = response.get("name")
        full_name = name.get("fullName") if isinstance(name, dict) else None
        if not isinstance(full_name, str) or not full_name.strip():
            full_name = None

        org_unit_path = response.get("orgUnitPath")
        if not isinstance(org_unit_path, str) or not org_unit_path.strip():
            org_unit_path = None

        archived = response.get("archived")
        mailbox_setup = response.get("isMailboxSetup")
        return GoogleWorkspaceUserLookupResult(
            id=google_user_id,
            customer_id=customer_id,
            full_name=full_name,
            primary_email=primary_email,
            aliases=aliases,
            non_editable_aliases=non_editable_aliases,
            suspended=response.get("suspended") is True,
            archived=archived if isinstance(archived, bool) else None,
            org_unit_path=org_unit_path,
            is_mailbox_setup=mailbox_setup if isinstance(mailbox_setup, bool) else None,
            matched_by=matched_by,
        )

    @staticmethod
    def _string_list(value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        return [item for item in value if isinstance(item, str)]

    @staticmethod
    def _match_type(
        searched_email: str,
        primary_email: str,
        aliases: list[str],
        non_editable_aliases: list[str],
    ) -> MatchType:
        if searched_email == primary_email.casefold():
            return "primary_email"
        if any(searched_email == alias.casefold() for alias in aliases):
            return "alias"
        if any(searched_email == alias.casefold() for alias in non_editable_aliases):
            return "non_editable_alias"
        raise GoogleWorkspaceError(GoogleWorkspaceErrorCode.GOOGLE_USER_LOOKUP_MISMATCH)
