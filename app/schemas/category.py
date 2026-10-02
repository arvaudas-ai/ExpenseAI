from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.category import VALID_COLORS, VALID_ICONS


class ExpenseCategoryBase(BaseModel):
    name: str
    icon: str = "other"
    color: str = "#95A5A6"

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        cleaned = str(value).strip()
        if not cleaned:
            raise ValueError("Category name is required.")
        if len(cleaned) > 100:
            raise ValueError("Category name must be 100 characters or fewer.")
        # Prevent XSS while allowing common business names and default categories
        if not all(c.isalnum() or c in " &-_" for c in cleaned):
            raise ValueError("Category name can only contain letters, numbers, spaces, ampersands, hyphens, and underscores.")
        return cleaned

    @field_validator("icon")
    @classmethod
    def validate_icon(cls, value: str) -> str:
        icon = str(value).strip().lower()
        if icon not in VALID_ICONS:
            raise ValueError(f"Invalid icon. Must be one of: {', '.join(sorted(VALID_ICONS))}")
        return icon

    @field_validator("color")
    @classmethod
    def validate_color(cls, value: str) -> str:
        color = str(value).strip().upper()
        if color not in VALID_COLORS:
            raise ValueError(f"Invalid color. Must be one of: {', '.join(sorted(VALID_COLORS))}")
        return color


class ExpenseCategoryCreate(ExpenseCategoryBase):
    pass


class ExpenseCategoryUpdate(BaseModel):
    name: str | None = None
    icon: str | None = None
    color: str | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str | None) -> str | None:
        if value is None:
            return value
        cleaned = str(value).strip()
        if not cleaned:
            raise ValueError("Category name is required.")
        if len(cleaned) > 100:
            raise ValueError("Category name must be 100 characters or fewer.")
        if not all(c.isalnum() or c in " &-_" for c in cleaned):
            raise ValueError("Category name can only contain letters, numbers, spaces, ampersands, hyphens, and underscores.")
        return cleaned

    @field_validator("icon")
    @classmethod
    def validate_icon(cls, value: str | None) -> str | None:
        if value is None:
            return value
        icon = str(value).strip().lower()
        if icon not in VALID_ICONS:
            raise ValueError(f"Invalid icon. Must be one of: {', '.join(sorted(VALID_ICONS))}")
        return icon

    @field_validator("color")
    @classmethod
    def validate_color(cls, value: str | None) -> str | None:
        if value is None:
            return value
        color = str(value).strip().upper()
        if color not in VALID_COLORS:
            raise ValueError(f"Invalid color. Must be one of: {', '.join(sorted(VALID_COLORS))}")
        return color


class ExpenseCategoryRead(ExpenseCategoryBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    is_default: bool
    created_at: datetime
    updated_at: datetime
