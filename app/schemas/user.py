import re
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, EmailStr, StringConstraints, field_validator

Password = Annotated[str, StringConstraints(min_length=8, max_length=14)]

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
    role: str
    has_subscription: bool
    bank_account_id: str | None = None
    oauth_provider: str | None = None
    require_password_reset: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class UserUpdate(BaseModel):
    email: EmailStr | None = None
    password: Password | None = None
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
