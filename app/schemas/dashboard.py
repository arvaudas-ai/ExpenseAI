from __future__ import annotations

from pydantic import BaseModel

from app.schemas.expense import ExpenseRead


class CategorySpending(BaseModel):
    name: str
    icon: str
    color: str
    total: float
    expense_count: int


class MonthlySpending(BaseModel):
    month: str
    label: str
    total: float
    expense_count: int


class PaymentMethodSpending(BaseModel):
    payment_method: str
    total: float
    expense_count: int


class DashboardInsights(BaseModel):
    highest_spending_category: str | None
    highest_spending_month: str | None
    month_over_month_change_percent: float | None


class DashboardSummary(BaseModel):
    currency: str
    total_spending: float
    expense_count: int
    spending_by_category: list[CategorySpending]
    recent_expenses: list[ExpenseRead]
    highest_expenses: list[ExpenseRead]
    monthly_spending: list[MonthlySpending]
    payment_method_spending: list[PaymentMethodSpending]
    insights: DashboardInsights
