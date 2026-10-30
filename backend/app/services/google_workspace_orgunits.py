from __future__ import annotations

import logging
import re
from dataclasses import dataclass, replace
from typing import Any
from uuid import UUID

from googleapiclient.errors import HttpError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.connectors.google_workspace_client import GoogleWorkspaceClientFactory
from app.connectors.google_workspace_credentials import DIRECTORY_ORGUNIT_READONLY_SCOPE
from app.connectors.google_workspace_errors import (
    GoogleWorkspaceError,
    GoogleWorkspaceErrorCode,
    map_google_api_error,
)
from app.models import ConnectorConfig, User
from app.services.google_workspace_user_lookup import GoogleWorkspaceUserLookup

logger = logging.getLogger(__name__)

ORGUNIT_FIELDS = (
    "orgUnitId,name,description,orgUnitPath,parentOrgUnitId,parentOrgUnitPath"
)
ORGUNIT_LIST_FIELDS = f"organizationUnits({ORGUNIT_FIELDS})"
MAX_ORGANIZATIONAL_UNITS = 10_000
ORGUNIT_ID_PATTERN = re.compile(r"^[A-Za-z0-9:_-]+$")


@dataclass(frozen=True)
class OrganizationalUnit:
    id: str
    name: str
    description: str | None
    path: str
    parent_id: str | None
    parent_path: str | None


@dataclass(frozen=True)
class OrganizationalUnitTreeNode(OrganizationalUnit):
    children: tuple[OrganizationalUnitTreeNode, ...]


@dataclass(frozen=True)
class OrganizationalUnitHierarchy:
    roots: tuple[OrganizationalUnitTreeNode, ...]
    total: int


class GoogleWorkspaceOrganizationalUnits:
    """Read and safely normalize one verified customer's organizational units."""

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
    def from_settings(cls, db: Session) -> GoogleWorkspaceOrganizationalUnits:
        factory = GoogleWorkspaceClientFactory.from_settings(db)
        return cls(db, factory, GoogleWorkspaceUserLookup(factory))

    def list_hierarchy(
        self,
        *,
        actor: User,
        organization_id: UUID,
    ) -> OrganizationalUnitHierarchy:
        customer_id = self._verified_customer_id(actor, organization_id)
        client: Any | None = None
        try:
            client = self.client_factory.for_directory_orgunits(
                actor=actor,
                organization_id=organization_id,
                scopes=(DIRECTORY_ORGUNIT_READONLY_SCOPE,),
            )
            response = (
                client.orgunits()
                .list(
                    customerId=customer_id,
                    type="allIncludingParent",
                    fields=ORGUNIT_LIST_FIELDS,
                )
                .execute(num_retries=0)
            )
            return self._to_hierarchy(response)
        except GoogleWorkspaceError:
            raise
        except Exception as error:
            raise map_google_api_error(error) from None
        finally:
            self._close_client(client, organization_id)

    def get_organizational_unit(
        self,
        *,
        actor: User,
        organization_id: UUID,
        org_unit_id: str,
    ) -> OrganizationalUnit:
        customer_id = self._verified_customer_id(actor, organization_id)
        client: Any | None = None
        try:
            client = self.client_factory.for_directory_orgunits(
                actor=actor,
                organization_id=organization_id,
                scopes=(DIRECTORY_ORGUNIT_READONLY_SCOPE,),
            )
            response = (
                client.orgunits()
                .get(
                    customerId=customer_id,
                    orgUnitPath=org_unit_id,
                    fields=ORGUNIT_FIELDS,
                )
                .execute(num_retries=0)
            )
            unit = self._to_unit(response)
            if unit.id != org_unit_id:
                raise GoogleWorkspaceError(
                    GoogleWorkspaceErrorCode.GOOGLE_ORGUNIT_LOOKUP_MISMATCH
                )
            return unit
        except GoogleWorkspaceError:
            raise
        except HttpError as error:
            if error.resp.status == 404:
                raise GoogleWorkspaceError(
                    GoogleWorkspaceErrorCode.GOOGLE_ORGUNIT_NOT_FOUND
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
    def _to_hierarchy(response: Any) -> OrganizationalUnitHierarchy:
        if not isinstance(response, dict):
            raise GoogleWorkspaceError(GoogleWorkspaceErrorCode.GOOGLE_API_ERROR)
        raw_units = response.get("organizationUnits", [])
        if not isinstance(raw_units, list):
            raise GoogleWorkspaceError(GoogleWorkspaceErrorCode.GOOGLE_API_ERROR)
        if len(raw_units) > MAX_ORGANIZATIONAL_UNITS:
            raise GoogleWorkspaceError(
                GoogleWorkspaceErrorCode.GOOGLE_OPERATION_BUDGET_EXCEEDED
            )
        if not raw_units:
            return OrganizationalUnitHierarchy(roots=(), total=0)

        units: dict[str, OrganizationalUnit] = {}
        paths: dict[str, str] = {}
        for value in raw_units:
            unit = GoogleWorkspaceOrganizationalUnits._to_unit(value)
            if unit.id in units or unit.path in paths:
                raise GoogleWorkspaceError(
                    GoogleWorkspaceErrorCode.GOOGLE_ORGUNIT_HIERARCHY_INVALID
                )
            units[unit.id] = unit
            paths[unit.path] = unit.id

        roots = [unit for unit in units.values() if unit.path == "/"]
        if len(roots) != 1:
            raise GoogleWorkspaceError(
                GoogleWorkspaceErrorCode.GOOGLE_ORGUNIT_HIERARCHY_INVALID
            )
        root = roots[0]
        if root.parent_id is not None or root.parent_path is not None:
            raise GoogleWorkspaceError(
                GoogleWorkspaceErrorCode.GOOGLE_ORGUNIT_HIERARCHY_INVALID
            )

        resolved: dict[str, OrganizationalUnit] = {root.id: root}
        parent_by_id: dict[str, str] = {}
        for unit in units.values():
            if unit.id == root.id:
                continue
            parent_from_id = units.get(unit.parent_id) if unit.parent_id else None
            parent_path_id = paths.get(unit.parent_path) if unit.parent_path else None
            parent_from_path = units.get(parent_path_id) if parent_path_id else None
            if unit.parent_id and parent_from_id is None:
                GoogleWorkspaceOrganizationalUnits._invalid_hierarchy()
            if unit.parent_path and parent_from_path is None:
                GoogleWorkspaceOrganizationalUnits._invalid_hierarchy()
            if parent_from_id and parent_from_path and parent_from_id.id != parent_from_path.id:
                GoogleWorkspaceOrganizationalUnits._invalid_hierarchy()
            parent = parent_from_id or parent_from_path
            if parent is None or parent.id == unit.id:
                GoogleWorkspaceOrganizationalUnits._invalid_hierarchy()
            expected_path = f"/{unit.name}" if parent.path == "/" else f"{parent.path}/{unit.name}"
            if unit.path != expected_path:
                GoogleWorkspaceOrganizationalUnits._invalid_hierarchy()
            parent_by_id[unit.id] = parent.id
            resolved[unit.id] = replace(
                unit,
                parent_id=parent.id,
                parent_path=parent.path,
            )

        GoogleWorkspaceOrganizationalUnits._validate_acyclic(root.id, resolved, parent_by_id)
        children: dict[str, list[str]] = {unit_id: [] for unit_id in resolved}
        for child_id, parent_id in parent_by_id.items():
            children[parent_id].append(child_id)
        for child_ids in children.values():
            child_ids.sort(key=lambda item: (resolved[item].path.casefold(), item))

        def build(unit_id: str) -> OrganizationalUnitTreeNode:
            unit = resolved[unit_id]
            return OrganizationalUnitTreeNode(
                **unit.__dict__,
                children=tuple(build(child_id) for child_id in children[unit_id]),
            )

        tree = build(root.id)
        return OrganizationalUnitHierarchy(roots=(tree,), total=len(resolved))

    @staticmethod
    def _validate_acyclic(
        root_id: str,
        units: dict[str, OrganizationalUnit],
        parent_by_id: dict[str, str],
    ) -> None:
        for unit_id in units:
            visited: set[str] = set()
            current = unit_id
            while current != root_id:
                if current in visited:
                    GoogleWorkspaceOrganizationalUnits._invalid_hierarchy()
                visited.add(current)
                parent = parent_by_id.get(current)
                if parent is None:
                    GoogleWorkspaceOrganizationalUnits._invalid_hierarchy()
                current = parent

    @staticmethod
    def _to_unit(value: Any) -> OrganizationalUnit:
        if not isinstance(value, dict):
            raise GoogleWorkspaceError(
                GoogleWorkspaceErrorCode.GOOGLE_ORGUNIT_HIERARCHY_INVALID
            )
        unit_id = GoogleWorkspaceOrganizationalUnits._required_string(
            value.get("orgUnitId"), 256
        )
        name = GoogleWorkspaceOrganizationalUnits._required_string(value.get("name"), 256)
        path = GoogleWorkspaceOrganizationalUnits._required_string(
            value.get("orgUnitPath"), 1000
        )
        if not path.startswith("/") or any(ord(character) < 32 for character in path):
            GoogleWorkspaceOrganizationalUnits._invalid_hierarchy()
        if not ORGUNIT_ID_PATTERN.fullmatch(unit_id):
            GoogleWorkspaceOrganizationalUnits._invalid_hierarchy()
        if "/" in name or any(ord(character) < 32 for character in name):
            GoogleWorkspaceOrganizationalUnits._invalid_hierarchy()
        parent_id = GoogleWorkspaceOrganizationalUnits._optional_string(
            value.get("parentOrgUnitId"), 256
        )
        parent_path = GoogleWorkspaceOrganizationalUnits._optional_string(
            value.get("parentOrgUnitPath"), 1000
        )
        if parent_id is not None and not ORGUNIT_ID_PATTERN.fullmatch(parent_id):
            GoogleWorkspaceOrganizationalUnits._invalid_hierarchy()
        if parent_path is not None and (
            not parent_path.startswith("/")
            or any(ord(character) < 32 for character in parent_path)
        ):
            GoogleWorkspaceOrganizationalUnits._invalid_hierarchy()
        return OrganizationalUnit(
            id=unit_id,
            name=name,
            description=GoogleWorkspaceOrganizationalUnits._optional_string(
                value.get("description"), 4096
            ),
            path=path,
            parent_id=parent_id,
            parent_path=parent_path,
        )

    @staticmethod
    def _required_string(value: Any, maximum: int) -> str:
        if not isinstance(value, str) or not value.strip() or len(value) > maximum:
            GoogleWorkspaceOrganizationalUnits._invalid_hierarchy()
        return value.strip()

    @staticmethod
    def _optional_string(value: Any, maximum: int) -> str | None:
        if value is None or value == "":
            return None
        if not isinstance(value, str) or len(value) > maximum:
            GoogleWorkspaceOrganizationalUnits._invalid_hierarchy()
        normalized = value.strip()
        return normalized or None

    @staticmethod
    def _invalid_hierarchy() -> None:
        raise GoogleWorkspaceError(
            GoogleWorkspaceErrorCode.GOOGLE_ORGUNIT_HIERARCHY_INVALID
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
                    "Closing Google organizational-units client failed organization_id=%s",
                    organization_id,
                )
