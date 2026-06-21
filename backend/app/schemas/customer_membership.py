import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

CustomerMembershipRole = Literal["customer_admin", "customer_user", "customer_viewer"]


class CustomerMembershipCreate(BaseModel):
    user_email: str = Field(..., min_length=1, max_length=255)
    role: CustomerMembershipRole
    is_active: bool = True


class CustomerMembershipUpdate(BaseModel):
    role: CustomerMembershipRole | None = None
    is_active: bool | None = None


class CustomerMembershipRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    customer_id: uuid.UUID
    role: CustomerMembershipRole
    is_active: bool
    created_at: datetime
    updated_at: datetime


class UserCustomerMembershipRead(BaseModel):
    customer_id: uuid.UUID
    customer_name: str
    role: CustomerMembershipRole
    is_active: bool
