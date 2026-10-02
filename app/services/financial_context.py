from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any

from sqlalchemy.orm import Session, joinedload

from app.models.expense import Expense
from app.models.user import User


def _month_start(value: date) -> date:
    return value.replace(day=1)


def _previous_month_start(value: date) -> date:
    current = _month_start(value)
    return date(current.year - 1, 12, 1) if current.month == 1 else date(current.year, current.month - 1, 1)


def build_financial_context(current_user: User, db: Session, today: date | None = None) -> dict[str, Any]:
    reference_date = today or date.today()
    current_start = _month_start(reference_date)
    previous_start = _previous_month_start(reference_date)
    expenses = (
        db.query(Expense)
        .options(joinedload(Expense.category))
        .filter(Expense.user_id == current_user.id)
        .order_by(Expense.date.desc(), Expense.id.desc())
        .all()
    )

    total_spending = sum(float(expense.amount) for expense in expenses)
    category_totals: dict[str, float] = defaultdict(float)
    payment_totals: dict[str, float] = defaultdict(float)
    current_total = 0.0
    current_count = 0
    previous_total = 0.0
    previous_count = 0

    for expense in expenses:
        amount = float(expense.amount)
        category_name = expense.category.name if expense.category else "Uncategorized"
        category_totals[category_name] += amount
        payment_totals[expense.payment_method] += amount
        if expense.date >= current_start:
            current_total += amount
            current_count += 1
        elif previous_start <= expense.date < current_start:
            previous_total += amount
            previous_count += 1

    category_items = [
        {"name": name, "total": round(total, 2)}
        for name, total in sorted(category_totals.items(), key=lambda item: item[1], reverse=True)
    ]
    highest_expenses = [
        {
            "description": expense.description,
            "amount": round(float(expense.amount), 2),
            "date": expense.date.isoformat(),
            "category": expense.category.name if expense.category else "Uncategorized",
        }
        for expense in sorted(expenses, key=lambda item: (float(item.amount), item.date), reverse=True)[:5]
    ]
    recent_expenses = [
        {
            "description": expense.description,
            "amount": round(float(expense.amount), 2),
            "date": expense.date.isoformat(),
            "category": expense.category.name if expense.category else "Uncategorized",
        }
        for expense in expenses[:5]
    ]

    month_change = None
    if previous_total:
        month_change = round(((current_total - previous_total) / previous_total) * 100, 2)

    return {
        "currency": current_user.currency,
        "reference_date": reference_date.isoformat(),
        "current_month": current_start.strftime("%B %Y"),
        "previous_month": previous_start.strftime("%B %Y"),
        "total_spending": round(total_spending, 2),
        "expense_count": len(expenses),
        "current_month_total": round(current_total, 2),
        "current_month_count": current_count,
        "previous_month_total": round(previous_total, 2),
        "previous_month_count": previous_count,
        "month_over_month_change_percent": month_change,
        "category_totals": category_items,
        "payment_method_totals": [{"method": name, "total": round(total, 2)} for name, total in sorted(payment_totals.items(), key=lambda item: item[1], reverse=True)],
        "highest_expenses": highest_expenses,
        "recent_expenses": recent_expenses,
    }
