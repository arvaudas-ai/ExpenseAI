from __future__ import annotations

from datetime import date as DateValue, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.category import VALID_COLORS, VALID_ICONS

VALID_PAYMENT_METHODS = {"cash", "credit_card", "debit_card", "bank_transfer", "digital_wallet", "other"}


class CategoryInfo(BaseModel):
    """Embedded category information for expense responses."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    icon: str
    color: str
    is_default: bool


class ExpenseBase(BaseModel):
    category_id: int
    amount: float = Field(gt=0, le=99999999.99, allow_inf_nan=False)
    description: str
    date: DateValue
    payment_method: str

    @field_validator("category_id")
    @classmethod
    def validate_category_id(cls, value: int) -> int:
        if value is None or value <= 0:
            raise ValueError("Category ID is required.")
        return value

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, value: float) -> float:
        if value is None or value <= 0:
            raise ValueError("Amount must be greater than zero.")
        return value

    @field_validator("description")
    @classmethod
    def validate_description(cls, value: str) -> str:
        cleaned = str(value).strip()
        if not cleaned:
            raise ValueError("Description is required.")
        if len(cleaned) > 500:
            raise ValueError("Description must be 500 characters or fewer.")
        return cleaned

    @field_validator("payment_method")
    @classmethod
    def validate_payment_method(cls, value: str) -> str:
        cleaned = str(value).strip().lower()
        if not cleaned:
            raise ValueError("Payment method is required.")
        if cleaned not in VALID_PAYMENT_METHODS:
            raise ValueError("Payment method is invalid.")
        return cleaned

    @field_validator("date")
    @classmethod
    def validate_date(cls, value: DateValue) -> DateValue:
        if value is None:
            raise ValueError("Date is required.")
        return value


class ExpenseCreate(ExpenseBase):
    pass


class ExpenseUpdate(BaseModel):
    category_id: int | None = None
    amount: float | None = Field(default=None, gt=0, le=99999999.99, allow_inf_nan=False)
    description: str | None = None
    date: DateValue | None = None
    payment_method: str | None = None

    @field_validator("category_id")
    @classmethod
    def validate_category_id(cls, value: int | None) -> int | None:
        if value is None:
            return value
        if value <= 0:
            raise ValueError("Category ID is required.")
        return value

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, value: float | None) -> float | None:
        if value is None:
            return value
        if value <= 0:
            raise ValueError("Amount must be greater than zero.")
        return value

    @field_validator("description")
    @classmethod
    def validate_description(cls, value: str | None) -> str | None:
        if value is None:
            return value
        cleaned = str(value).strip()
        if not cleaned:
            raise ValueError("Description is required.")
        if len(cleaned) > 500:
            raise ValueError("Description must be 500 characters or fewer.")
        return cleaned

    @field_validator("payment_method")
    @classmethod
    def validate_payment_method(cls, value: str | None) -> str | None:
        if value is None:
            return value
        cleaned = str(value).strip().lower()
        if not cleaned:
            raise ValueError("Payment method is required.")
        if cleaned not in VALID_PAYMENT_METHODS:
            raise ValueError("Payment method is invalid.")
        return cleaned

    @field_validator("date")
    @classmethod
    def validate_date(cls, value: DateValue | None) -> DateValue | None:
        if value is None:
            return value
        return value


class ExpenseRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    category_id: int | None
    category: CategoryInfo | None
    amount: float
    description: str
    date: DateValue
    payment_method: str
    created_at: datetime
    updated_at: datetime
