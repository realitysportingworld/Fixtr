import re
from uuid import UUID
from pydantic import BaseModel, EmailStr, Field, field_validator

from app.core.security import BCRYPT_MAX_BYTES

USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{3,30}$")


class RegisterRequest(BaseModel):
    email: EmailStr
    username: str
    password: str = Field(min_length=8)

    @field_validator("email")
    @classmethod
    def normalise_email(cls, v):
        return v.strip().lower()

    @field_validator("username")
    @classmethod
    def username_valid(cls, v):
        v = v.strip()
        if not USERNAME_PATTERN.match(v):
            raise ValueError("must be 3-30 characters: letters, numbers, '_', '.' or '-'")
        return v

    @field_validator("password")
    @classmethod
    def password_length(cls, v):
        # Length over composition rules (NIST SP 800-63B); bcrypt caps input at 72 bytes
        if len(v.encode("utf-8")) > BCRYPT_MAX_BYTES:
            raise ValueError(f"must be at most {BCRYPT_MAX_BYTES} bytes")
        if not v.strip():
            raise ValueError("must not be blank")
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: UUID
    email: str
    username: str
    is_premium: bool

    class Config:
        from_attributes = True
