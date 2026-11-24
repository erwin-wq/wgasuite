from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.connectors.google_workspace_client import GoogleWorkspaceClientFactory
from app.connectors.google_workspace_credentials import DIRECTORY_DOMAIN_READONLY_SCOPE
from app.connectors.google_workspace_errors import (
    GoogleWorkspaceError,
    GoogleWorkspaceErrorCode,
    map_google_api_error,
)
from app.models import ConnectorConfig, User
from app.services.google_workspace_user_lookup import GoogleWorkspaceUserLookup

logger = logging.getLogger(__name__)

DOMAIN_FIELDS = (
    "domainName,isPrimary,verified,creationTime,"
    "domainAliases(domainAliasName,parentDomainName,verified,creationTime)"
)
DOMAIN_LIST_FIELDS = f"domains({DOMAIN_FIELDS})"
DOMAIN_ALIAS_FIELDS = "domainAliasName,parentDomainName,verified,creationTime"
DOMAIN_ALIAS_LIST_FIELDS = f"domainAliases({DOMAIN_ALIAS_FIELDS})"
MAX_DOMAIN_RECORDS = 10_000


@dataclass(frozen=True)
class WorkspaceDomain:
    name: str
    kind: Literal["primary", "secondary", "domain"]
    verified: bool | None
    creation_time: int | None


@dataclass(frozen=True)
class WorkspaceDomainAlias:
    name: str
    parent_domain: str
    verified: bool | None
    creation_time: int | None


@dataclass(frozen=True)
class WorkspaceDomainInventory:
    domains: tuple[WorkspaceDomain, ...]
    aliases: tuple[WorkspaceDomainAlias, ...]


class GoogleWorkspaceDomains:
    """Read one verified customer's domains and reconcile duplicate alias sources."""

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
    def from_settings(cls, db: Session) -> GoogleWorkspaceDomains:
        factory = GoogleWorkspaceClientFactory.from_settings(db)
        return cls(db, factory, GoogleWorkspaceUserLookup(factory))

    def list_inventory(
        self,
        *,
        actor: User,
        organization_id: UUID,
        request_timeout_seconds: float | None = None,
    ) -> WorkspaceDomainInventory:
        customer_id = self._verified_customer_id(actor, organization_id)
        client: Any | None = None
        try:
            arguments: dict[str, Any] = {
                "actor": actor,
                "organization_id": organization_id,
                "scopes": (DIRECTORY_DOMAIN_READONLY_SCOPE,),
            }
            if request_timeout_seconds is not None:
                arguments["request_timeout_seconds"] = request_timeout_seconds
            client = self.client_factory.for_directory_domains(**arguments)
            domains_response = (
                client.domains()
                .list(customer=customer_id, fields=DOMAIN_LIST_FIELDS)
                .execute(num_retries=0)
            )
            aliases_response = (
                client.domainAliases()
                .list(customer=customer_id, fields=DOMAIN_ALIAS_LIST_FIELDS)
                .execute(num_retries=0)
            )
            return self._normalize(domains_response, aliases_response)
        except GoogleWorkspaceError:
            raise
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

    @classmethod
    def _normalize(cls, domains_response: Any, aliases_response: Any) -> WorkspaceDomainInventory:
        raw_domains = cls._list_field(domains_response, "domains")
        raw_dedicated_aliases = cls._list_field(aliases_response, "domainAliases")
        if len(raw_domains) + len(raw_dedicated_aliases) > MAX_DOMAIN_RECORDS:
            raise GoogleWorkspaceError(GoogleWorkspaceErrorCode.GOOGLE_OPERATION_BUDGET_EXCEEDED)

        domains: dict[str, WorkspaceDomain] = {}
        nested_aliases: list[WorkspaceDomainAlias] = []
        for raw_domain in raw_domains:
            if not isinstance(raw_domain, dict):
                cls._invalid_response()
            name = cls._name(raw_domain.get("domainName"))
            key = name.casefold()
            if key in domains:
                cls._invalid_response()
            is_primary = cls._optional_bool(raw_domain.get("isPrimary"))
            domains[key] = WorkspaceDomain(
                name=name,
                kind="primary"
                if is_primary is True
                else "secondary"
                if is_primary is False
                else "domain",
                verified=cls._optional_bool(raw_domain.get("verified")),
                creation_time=cls._optional_timestamp(raw_domain.get("creationTime")),
            )
            embedded = raw_domain.get("domainAliases", [])
            if embedded is None:
                embedded = []
            if not isinstance(embedded, list):
                cls._invalid_response()
            nested_aliases.extend(cls._alias(value) for value in embedded)

        aliases: dict[str, WorkspaceDomainAlias] = {}
        for alias in [*nested_aliases, *(cls._alias(value) for value in raw_dedicated_aliases)]:
            key = alias.name.casefold()
            existing = aliases.get(key)
            if existing is not None and not cls._aliases_compatible(existing, alias):
                cls._invalid_response()
            aliases[key] = cls._merge_alias(existing, alias) if existing else alias

        domain_keys = set(domains)
        if sum(domain.kind == "primary" for domain in domains.values()) > 1:
            cls._invalid_response()
        if any(alias.parent_domain.casefold() not in domain_keys for alias in aliases.values()):
            cls._invalid_response()

        ordered_domains = tuple(
            sorted(
                domains.values(), key=lambda item: (item.kind != "primary", item.name.casefold())
            )
        )
        ordered_aliases = tuple(sorted(aliases.values(), key=lambda item: item.name.casefold()))
        return WorkspaceDomainInventory(domains=ordered_domains, aliases=ordered_aliases)

    @classmethod
    def _alias(cls, value: Any) -> WorkspaceDomainAlias:
        if not isinstance(value, dict):
            cls._invalid_response()
        return WorkspaceDomainAlias(
            name=cls._name(value.get("domainAliasName")),
            parent_domain=cls._name(value.get("parentDomainName")),
            verified=cls._optional_bool(value.get("verified")),
            creation_time=cls._optional_timestamp(value.get("creationTime")),
        )

    @staticmethod
    def _aliases_compatible(left: WorkspaceDomainAlias, right: WorkspaceDomainAlias) -> bool:
        return (
            left.parent_domain.casefold() == right.parent_domain.casefold()
            and (left.verified is None or right.verified is None or left.verified == right.verified)
            and (
                left.creation_time is None
                or right.creation_time is None
                or left.creation_time == right.creation_time
            )
        )

    @staticmethod
    def _merge_alias(
        left: WorkspaceDomainAlias, right: WorkspaceDomainAlias
    ) -> WorkspaceDomainAlias:
        return WorkspaceDomainAlias(
            name=right.name,
            parent_domain=right.parent_domain,
            verified=right.verified if right.verified is not None else left.verified,
            creation_time=(
                right.creation_time if right.creation_time is not None else left.creation_time
            ),
        )

    @classmethod
    def _list_field(cls, response: Any, field: str) -> list[Any]:
        if not isinstance(response, dict):
            cls._invalid_response()
        value = response.get(field, [])
        if value is None:
            return []
        if not isinstance(value, list):
            cls._invalid_response()
        return value

    @classmethod
    def _name(cls, value: Any) -> str:
        if not isinstance(value, str):
            cls._invalid_response()
        normalized = value.strip()
        if not normalized or len(normalized) > 253 or any(ord(char) < 33 for char in normalized):
            cls._invalid_response()
        return normalized

    @classmethod
    def _optional_bool(cls, value: Any) -> bool | None:
        if value is None:
            return None
        if not isinstance(value, bool):
            cls._invalid_response()
        return value

    @classmethod
    def _optional_timestamp(cls, value: Any) -> int | None:
        if value is None or value == "":
            return None
        if isinstance(value, bool) or not isinstance(value, (str, int)):
            cls._invalid_response()
        try:
            timestamp = int(value)
        except ValueError:
            cls._invalid_response()
        if timestamp < 0:
            cls._invalid_response()
        return timestamp

    @staticmethod
    def _invalid_response() -> None:
        raise GoogleWorkspaceError(GoogleWorkspaceErrorCode.GOOGLE_API_ERROR)

    @staticmethod
    def _close_client(client: Any | None, organization_id: UUID) -> None:
        if client is None:
            return
        try:
            close = getattr(client, "close", None)
            if callable(close):
                close()
        except Exception:
            logger.warning(
                "Directory domains client close failed organization_id=%s", organization_id
            )
