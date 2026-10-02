import json
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class UserBase(BaseModel):
    name: str
    email: EmailStr
    currency: str = "USD"
    preferences: dict[str, Any] = Field(default_factory=dict)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Full name is required.")
        return cleaned

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: EmailStr) -> str:
        cleaned = str(value).strip().lower()
        return cleaned

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, value: str) -> str:
        cleaned = str(value or "USD").strip().upper()
        if not cleaned:
            return "USD"
        return cleaned

    @field_validator("preferences", mode="before")
    @classmethod
    def validate_preferences(cls, value: Any) -> dict[str, Any]:
        if value is None:
            return {}
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError:
                return {}
            if isinstance(parsed, dict):
                return parsed
            return {"value": parsed}
        if isinstance(value, dict):
            return value
        return {}


class UserCreate(UserBase):
    password: str
    password_confirmation: str

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        if len(value) < 8:
            raise ValueError("Password must be at least 8 characters long.")
        return value


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserRead(UserBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserRead


class UserUpdate(BaseModel):
    name: str | None = None
    email: EmailStr | None = None
    currency: str | None = None
    preferences: dict[str, Any] | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str | None) -> str | None:
        if value is None:
            return value
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Full name is required.")
        return cleaned

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: EmailStr | None) -> str | None:
        if value is None:
            return value
        return str(value).strip().lower()

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, value: str | None) -> str | None:
        if value is None:
            return value
        cleaned = str(value).strip().upper()
        if not cleaned:
            raise ValueError("Currency is required.")
        return cleaned

    @field_validator("preferences", mode="before")
    @classmethod
    def validate_preferences(cls, value: Any) -> dict[str, Any] | None:
        if value is None:
            return None
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError as exc:
                raise ValueError("Preferences must be valid JSON.") from exc
            if not isinstance(parsed, dict):
                raise ValueError("Preferences must be a JSON object.")
            return parsed
        if isinstance(value, dict):
            return value
        raise ValueError("Preferences must be a JSON object.")


class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str
    confirm_new_password: str

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, value: str) -> str:
        if len(value) < 8:
            raise ValueError("New password must be at least 8 characters long.")
        return value
