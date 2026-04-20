import re
from datetime import datetime
from typing import Annotated, Any

from pydantic import BaseModel, EmailStr, StringConstraints, field_validator

# Fix: max_length raised from 14 → 72 (bcrypt limit; longer passwords are better security)
Password = Annotated[str, StringConstraints(min_length=8, max_length=72)]


class UserCreate(BaseModel):
    email: EmailStr
    password: Password
    role: str = "regular"

    @field_validator("password")
    @classmethod
    def strong_password(cls, v: str) -> str:
        if not re.search(r"\d", v):
            raise ValueError("Password must include at least one digit")
        if not re.search(r"[@$!%*?&]", v):
            raise ValueError("Password must include at least one special character @$!%*?&")
        return v


class UserResponse(BaseModel):
    id: int
    email: EmailStr
    name: str | None = None
    role: str
    has_subscription: bool
    bank_account_id: str | None = None
    oauth_provider: str | None = None
    require_password_reset: bool
    calendar_providers: list[str] = []
    created_at: datetime

    @field_validator("calendar_providers", mode="before")
    @classmethod
    def coerce_none_to_list(cls, v: Any) -> list[str]:
        return v if v is not None else []

    updated_at: datetime

    class Config:
        from_attributes = True


class UserUpdate(BaseModel):
    email: EmailStr | None = None
    password: Password | None = None
    name: str | None = None
    role: str | None = None
    has_subscription: bool | None = None
    bank_account_id: str | None = None

    @field_validator("password")
    @classmethod
    def strong_password(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if not re.search(r"\d", v):
            raise ValueError("Password must include at least one digit")
        if not re.search(r"[@$!%*?&]", v):
            raise ValueError("Password must include at least one special character @$!%*?&")
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class TokenPayload(BaseModel):
    sub: str
    exp: int
    iat: int
