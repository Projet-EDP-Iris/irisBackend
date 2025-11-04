from typing import Annotated
from pydantic import BaseModel, EmailStr, StringConstraints, field_validator
import re

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
