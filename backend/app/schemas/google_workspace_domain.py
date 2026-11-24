from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class GoogleWorkspaceDomainReferenceRequest(BaseModel):
    name: str = Field(min_length=1, max_length=254)


class GoogleWorkspaceDomainRead(BaseModel):
    name: str
    kind: Literal["primary", "secondary", "domain"]
    verified: bool | None
    creation_time: int | None


class GoogleWorkspaceDomainAliasRead(BaseModel):
    name: str
    parent_domain: str
    kind: Literal["alias"] = "alias"
    verified: bool | None
    creation_time: int | None


class GoogleWorkspaceDomainInventoryRead(BaseModel):
    domains: list[GoogleWorkspaceDomainRead]
    aliases: list[GoogleWorkspaceDomainAliasRead]
    domain_count: int
    alias_count: int
    read_only: bool = True


class GoogleWorkspaceDomainDetailRead(BaseModel):
    domain: GoogleWorkspaceDomainRead
    aliases: list[GoogleWorkspaceDomainAliasRead]
    read_only: bool = True


class GoogleWorkspaceDomainAliasDetailRead(BaseModel):
    alias: GoogleWorkspaceDomainAliasRead
    read_only: bool = True
