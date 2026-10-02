from __future__ import annotations

import csv
import io
from collections import defaultdict
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session, joinedload

from app.api.dependencies import CurrentUser
from app.db.session import get_db
from app.models.expense import Expense
from app.schemas.dashboard import CategorySpending, DashboardInsights, DashboardSummary, MonthlySpending, PaymentMethodSpending
from app.schemas.expense import ExpenseRead

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


def _spreadsheet_safe(value: str) -> str:
    if value.lstrip(" \t\r\n\ufeff").startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def _month_offset(year: int, month: int, offset: int) -> tuple[int, int]:
    month_index = year * 12 + month - 1 + offset
    return month_index // 12, month_index % 12 + 1


def _month_key(year: int, month: int) -> str:
    return f"{year:04d}-{month:02d}"


def _month_range(start: date, end: date) -> list[tuple[int, int]]:
    months = []
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        months.append((year, month))
        year, month = _month_offset(year, month, 1)
    return months


def _validate_filters(
    start_date: date | None,
    end_date: date | None,
    category_id: int | None,
    payment_method: str | None,
) -> str | None:
    if start_date and end_date and start_date > end_date:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="start_date must be on or before end_date.")
    if category_id is not None and category_id <= 0:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="category_id must be positive.")
    if payment_method is not None:
        normalized = payment_method.strip().lower()
        allowed = {"cash", "credit_card", "debit_card", "bank_transfer", "digital_wallet", "other"}
        if normalized not in allowed:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="payment_method is invalid.")
        return normalized
    return None


def _filtered_expenses(
    current_user: CurrentUser,
    db: Session,
    start_date: date | None,
    end_date: date | None,
    category_id: int | None,
    payment_method: str | None,
) -> list[Expense]:
    query = db.query(Expense).options(joinedload(Expense.category)).filter(Expense.user_id == current_user.id)
    if start_date:
        query = query.filter(Expense.date >= start_date)
    if end_date:
        query = query.filter(Expense.date <= end_date)
    if category_id is not None:
        query = query.filter(Expense.category_id == category_id)
    if payment_method:
        query = query.filter(Expense.payment_method == payment_method)
    return query.order_by(Expense.date.desc(), Expense.id.desc()).all()


@router.get("/summary", response_model=DashboardSummary)
async def get_dashboard_summary(
    current_user: CurrentUser,
    db: Session = Depends(get_db),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    category_id: int | None = Query(default=None, gt=0),
    payment_method: str | None = Query(default=None),
) -> DashboardSummary:
    payment_method = _validate_filters(start_date, end_date, category_id, payment_method)
    expenses = _filtered_expenses(current_user, db, start_date, end_date, category_id, payment_method)

    category_totals: dict[int | None, dict[str, object]] = {}
    monthly_totals: dict[str, dict[str, object]] = defaultdict(lambda: {"total": 0.0, "expense_count": 0})
    payment_totals: dict[str, dict[str, object]] = defaultdict(lambda: {"total": 0.0, "expense_count": 0})
    total_spending = 0.0

    for expense in expenses:
        amount = float(expense.amount)
        total_spending += amount

        category = expense.category
        category_id = category.id if category else None
        if category_id not in category_totals:
            category_totals[category_id] = {
                "name": category.name if category else "Uncategorized",
                "icon": category.icon if category else "other",
                "color": category.color if category else "#95A5A6",
                "total": 0.0,
                "expense_count": 0,
            }
        category_totals[category_id]["total"] = float(category_totals[category_id]["total"]) + amount
        category_totals[category_id]["expense_count"] = int(category_totals[category_id]["expense_count"]) + 1

        month_key = expense.date.strftime("%Y-%m")
        monthly_totals[month_key]["total"] = float(monthly_totals[month_key]["total"]) + amount
        monthly_totals[month_key]["expense_count"] = int(monthly_totals[month_key]["expense_count"]) + 1
        payment_totals[expense.payment_method]["total"] = float(payment_totals[expense.payment_method]["total"]) + amount
        payment_totals[expense.payment_method]["expense_count"] = int(payment_totals[expense.payment_method]["expense_count"]) + 1

    if start_date or end_date:
        trend_start = start_date or (end_date.replace(day=1) if end_date else date.today().replace(day=1))
        trend_end = end_date or date.today()
        months = _month_range(trend_start, trend_end)
    else:
        today = date.today()
        months = [_month_offset(today.year, today.month, offset) for offset in range(-5, 1)]

    monthly_spending = []
    for year, month in months:
        month_key = _month_key(year, month)
        totals = monthly_totals[month_key]
        monthly_spending.append(
            MonthlySpending(
                month=month_key,
                label=date(year, month, 1).strftime("%b %Y"),
                total=float(totals["total"]),
                expense_count=int(totals["expense_count"]),
            )
        )

    spending_by_category = [
        CategorySpending(
            name=str(values["name"]),
            icon=str(values["icon"]),
            color=str(values["color"]),
            total=float(values["total"]),
            expense_count=int(values["expense_count"]),
        )
        for values in sorted(category_totals.values(), key=lambda item: float(item["total"]), reverse=True)
    ]

    month_values = [month.total for month in monthly_spending]
    month_over_month_change = None
    if len(month_values) >= 2 and month_values[-2] != 0:
        month_over_month_change = round(((month_values[-1] - month_values[-2]) / month_values[-2]) * 100, 2)

    highest_category = spending_by_category[0].name if spending_by_category else None
    highest_month = max(monthly_spending, key=lambda month: month.total).label if any(month_values) else None

    return DashboardSummary(
        currency=current_user.currency,
        total_spending=total_spending,
        expense_count=len(expenses),
        spending_by_category=spending_by_category,
        recent_expenses=[ExpenseRead.model_validate(expense) for expense in expenses[:5]],
        highest_expenses=[ExpenseRead.model_validate(expense) for expense in sorted(expenses, key=lambda item: (float(item.amount), item.date), reverse=True)[:5]],
        monthly_spending=monthly_spending,
        payment_method_spending=[
            PaymentMethodSpending(
                payment_method=method,
                total=float(values["total"]),
                expense_count=int(values["expense_count"]),
            )
            for method, values in sorted(payment_totals.items(), key=lambda item: float(item[1]["total"]), reverse=True)
        ],
        insights=DashboardInsights(
            highest_spending_category=highest_category,
            highest_spending_month=highest_month,
            month_over_month_change_percent=month_over_month_change,
        ),
    )


@router.get("/export.csv")
async def export_dashboard_csv(
    current_user: CurrentUser,
    db: Session = Depends(get_db),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    category_id: int | None = Query(default=None, gt=0),
    payment_method: str | None = Query(default=None),
) -> Response:
    payment_method = _validate_filters(start_date, end_date, category_id, payment_method)
    expenses = _filtered_expenses(current_user, db, start_date, end_date, category_id, payment_method)

    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(["date", "description", "category", "amount", "currency", "payment_method"])
    for expense in expenses:
        writer.writerow([
            expense.date.isoformat(),
            _spreadsheet_safe(expense.description),
            _spreadsheet_safe(expense.category.name if expense.category else "Uncategorized"),
            f"{float(expense.amount):.2f}",
            current_user.currency,
            expense.payment_method,
        ])

    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=expenseai-expenses.csv"},
    )
