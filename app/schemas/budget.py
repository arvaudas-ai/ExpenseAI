from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class BudgetCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    amount: Decimal = Field(gt=0, max_digits=10, decimal_places=2)
    period: Literal["monthly"] = "monthly"
    category_id: int | None = None

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Budget name is required.")
        return cleaned

    @field_validator("category_id")
    @classmethod
    def validate_category_id(cls, value: int | None) -> int | None:
        if value is not None and value <= 0:
            raise ValueError("Category ID must be positive.")
        return value


class BudgetUpdate(BudgetCreate):
    pass


class BudgetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    amount: float
    period: str
    category_id: int | None
    category_name: str
    period_start: date
    period_end: date
    spent: float
    remaining: float
    percent_used: float
    status: Literal["under", "near", "over"]
    created_at: datetime
    updated_at: datetime
