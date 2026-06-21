import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.customer_membership import UserCustomerMembershipRead


class LoginRequest(BaseModel):
    email: str = Field(..., min_length=1, max_length=255)
    password: str = Field(..., min_length=1)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    full_name: str
    role: str
    is_active: bool
    created_at: datetime
    customer_memberships: list[UserCustomerMembershipRead] = Field(default_factory=list)
