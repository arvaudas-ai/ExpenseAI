from __future__ import annotations

import re
from collections import defaultdict
from datetime import date
from typing import Any

from sqlalchemy import and_
from sqlalchemy.orm import Session

from app.models.category import ExpenseCategory
from app.models.expense import Expense
from app.models.user import User


def _month_offset(year: int, month: int, offset: int) -> tuple[int, int]:
    month_index = year * 12 + month - 1 + offset
    return month_index // 12, month_index % 12 + 1


def build_spending_analysis_stats(
    current_user: User,
    db: Session,
    today: date | None = None,
) -> dict[str, Any]:
    reference = today or date.today()
    current_month = reference.replace(day=1)
    month_keys = [_month_offset(current_month.year, current_month.month, offset) for offset in range(-11, 1)]
    start_date = date(month_keys[0][0], month_keys[0][1], 1)

    rows = (
        db.query(Expense.date, Expense.amount, Expense.payment_method, Expense.description, ExpenseCategory.name)
        .outerjoin(
            ExpenseCategory,
            and_(Expense.category_id == ExpenseCategory.id, ExpenseCategory.user_id == current_user.id),
        )
        .filter(Expense.user_id == current_user.id, Expense.date >= start_date, Expense.date <= reference)
        .order_by(Expense.date.asc(), Expense.id.asc())
        .all()
    )

    monthly: dict[tuple[int, int], dict[str, float | int]] = defaultdict(lambda: {"total": 0.0, "expense_count": 0})
    categories: dict[str, dict[str, float | int]] = defaultdict(lambda: {"total": 0.0, "expense_count": 0})
    payments: dict[str, dict[str, float | int]] = defaultdict(lambda: {"total": 0.0, "expense_count": 0})
    repeated_descriptions: dict[str, dict[str, Any]] = {}
    total = 0.0

    for expense_date, raw_amount, payment_method, description, category_name in rows:
        amount = float(raw_amount)
        month_key = (expense_date.year, expense_date.month)
        category = category_name or "Uncategorized"
        monthly[month_key]["total"] = float(monthly[month_key]["total"]) + amount
        monthly[month_key]["expense_count"] = int(monthly[month_key]["expense_count"]) + 1
        categories[category]["total"] = float(categories[category]["total"]) + amount
        categories[category]["expense_count"] = int(categories[category]["expense_count"]) + 1
        payments[payment_method]["total"] = float(payments[payment_method]["total"]) + amount
        payments[payment_method]["expense_count"] = int(payments[payment_method]["expense_count"]) + 1
        total += amount

        normalized_description = re.sub(r"\s+", " ", description.casefold()).strip()
        if normalized_description:
            group = repeated_descriptions.setdefault(
                normalized_description,
                {"category": category, "count": 0, "months": set(), "total": 0.0},
            )
            group["count"] += 1
            group["months"].add(month_key)
            group["total"] += amount

    monthly_totals = [float(monthly[key]["total"]) for key in month_keys]
    monthly_series = [
        {
            "month": f"{year:04d}-{month:02d}",
            "total": round(float(monthly[(year, month)]["total"]), 2),
            "expense_count": int(monthly[(year, month)]["expense_count"]),
        }
        for year, month in month_keys
    ]
    sorted_categories = [
        {
            "category": category,
            "total": round(float(values["total"]), 2),
            "expense_count": int(values["expense_count"]),
            "share_percent": round(float(values["total"]) / total * 100, 2) if total else 0.0,
        }
        for category, values in sorted(categories.items(), key=lambda item: float(item[1]["total"]), reverse=True)
    ]
    category_series = sorted_categories[:20]
    if len(sorted_categories) > 20:
        remaining_categories = sorted_categories[20:]
        remaining_total = sum(item["total"] for item in remaining_categories)
        category_series.append(
            {
                "category": "Other categories",
                "total": round(remaining_total, 2),
                "expense_count": sum(item["expense_count"] for item in remaining_categories),
                "share_percent": round(remaining_total / total * 100, 2) if total else 0.0,
            }
        )
    payment_series = [
        {"payment_method": method, "total": round(float(values["total"]), 2), "expense_count": int(values["expense_count"])}
        for method, values in sorted(payments.items(), key=lambda item: float(item[1]["total"]), reverse=True)
    ]

    current_total = monthly_totals[-1]
    previous_total = monthly_totals[-2]
    month_change = round((current_total - previous_total) / previous_total * 100, 2) if previous_total else None
    prior_active_totals = [value for value in monthly_totals[:-1] if value > 0]
    prior_active_average = sum(prior_active_totals) / len(prior_active_totals) if prior_active_totals else 0.0
    spike = None
    if len(prior_active_totals) >= 3 and prior_active_average and current_total > prior_active_average * 1.5:
        spike = {
            "month": f"{current_month.year:04d}-{current_month.month:02d}",
            "total": round(current_total, 2),
            "prior_active_month_average": round(prior_active_average, 2),
            "multiple_of_average": round(current_total / prior_active_average, 2),
        }

    recurring = [
        {
            "category": values["category"],
            "occurrences": values["count"],
            "active_months": len(values["months"]),
            "average_amount": round(values["total"] / values["count"], 2),
        }
        for values in repeated_descriptions.values()
        if values["count"] >= 3 and len(values["months"]) >= 2
    ]
    recurring.sort(key=lambda item: (item["active_months"], item["occurrences"]), reverse=True)

    active_months = len(prior_active_totals) + int(current_total > 0)
    return {
        "period_start": start_date.isoformat(),
        "period_end": reference.isoformat(),
        "currency": current_user.currency,
        "total_spending": round(total, 2),
        "expense_count": len(rows),
        "average_expense": round(total / len(rows), 2) if rows else 0.0,
        "monthly_average": round(sum(monthly_totals) / 12, 2),
        "months_with_expenses": active_months,
        "monthly_totals": monthly_series,
        "category_totals": category_series,
        "payment_method_totals": payment_series,
        "month_over_month": {
            "current_month": f"{current_month.year:04d}-{current_month.month:02d}",
            "current_total": round(current_total, 2),
            "previous_month": f"{month_keys[-2][0]:04d}-{month_keys[-2][1]:02d}",
            "previous_total": round(previous_total, 2),
            "change_percent": month_change,
        },
        "current_month_spike": spike,
        "recurring_patterns": recurring[:5],
        "has_enough_data": len(rows) >= 3,
    }
