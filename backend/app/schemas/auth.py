import re
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.core.security import BCRYPT_MAX_BYTES

USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{3,30}$")
MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_INPUT = 1_000  # for checks against an existing password; the hash only sees 72 bytes


def check_username(v: str) -> str:
    v = v.strip()
    if not USERNAME_PATTERN.match(v):
        raise ValueError("must be 3-30 characters: letters, numbers, '_', '.' or '-'")
    return v


def check_new_password(v: str) -> str:
    # Length over composition rules (NIST SP 800-63B); bcrypt caps input at 72 bytes
    if len(v.encode("utf-8")) > BCRYPT_MAX_BYTES:
        raise ValueError(f"must be at most {BCRYPT_MAX_BYTES} bytes")
    if not v.strip():
        raise ValueError("must not be blank")
    return v


class RegisterRequest(BaseModel):
    email: EmailStr
    username: str
    password: str = Field(min_length=MIN_PASSWORD_LENGTH)

    @field_validator("email")
    @classmethod
    def email_normalised(cls, v):
        return v.strip().lower()

    @field_validator("username")
    @classmethod
    def username_valid(cls, v):
        return check_username(v)

    @field_validator("password")
    @classmethod
    def password_valid(cls, v):
        return check_new_password(v)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(max_length=MAX_PASSWORD_INPUT)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    refresh_token: Optional[str] = None
    expires_in: Optional[int] = None  # seconds until the access token expires


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=1, max_length=200)


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    username: str
    is_premium: bool


class UpdateMeRequest(BaseModel):
    username: str

    @field_validator("username")
    @classmethod
    def username_valid(cls, v):
        return check_username(v)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(max_length=MAX_PASSWORD_INPUT)
    new_password: str = Field(min_length=MIN_PASSWORD_LENGTH)

    @field_validator("new_password")
    @classmethod
    def password_valid(cls, v):
        return check_new_password(v)


class ForgotPasswordRequest(BaseModel):
    email: EmailStr

    @field_validator("email")
    @classmethod
    def email_normalised(cls, v):
        return v.strip().lower()


class ResetPasswordRequest(BaseModel):
    email: EmailStr
    code: str = Field(pattern=r"^\s*\d{6}\s*$")
    new_password: str = Field(min_length=MIN_PASSWORD_LENGTH)

    @field_validator("email")
    @classmethod
    def email_normalised(cls, v):
        return v.strip().lower()

    @field_validator("code")
    @classmethod
    def code_trimmed(cls, v):
        return v.strip()

    @field_validator("new_password")
    @classmethod
    def password_valid(cls, v):
        return check_new_password(v)


class DeleteAccountRequest(BaseModel):
    password: str = Field(max_length=MAX_PASSWORD_INPUT)
