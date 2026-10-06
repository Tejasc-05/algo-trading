from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class PasswordRequest(BaseModel):
    @field_validator("password", check_fields=False)
    @classmethod
    def password_bytes(cls, value: str) -> str:
        if len(value.encode("utf-8")) > 72:
            raise ValueError("Password exceeds the 72-byte hashing limit")
        return value


class RegisterRequest(PasswordRequest):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str | None = Field(default=None, max_length=255)


class LoginRequest(PasswordRequest):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str
    full_name: str | None
    is_active: bool
    created_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut
