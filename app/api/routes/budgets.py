from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.api.dependencies import CurrentUser
from app.db.session import get_db
from app.models.budget import Budget
from app.models.category import ExpenseCategory
from app.models.expense import Expense
from app.schemas.budget import BudgetCreate, BudgetRead, BudgetUpdate

router = APIRouter(prefix="/api/budgets", tags=["budgets"])


def _month_bounds(today: date | None = None) -> tuple[date, date]:
    current = today or date.today()
    start = current.replace(day=1)
    if current.month == 12:
        next_month = date(current.year + 1, 1, 1)
    else:
        next_month = date(current.year, current.month + 1, 1)
    return start, next_month


def _budget_read(
    budget: Budget,
    db: Session,
    current_user: CurrentUser,
    today: date | None = None,
    spending_by_category: dict[int | None, float] | None = None,
) -> BudgetRead:
    period_start, next_period = _month_bounds(today)
    if spending_by_category is None:
        query = db.query(func.coalesce(func.sum(Expense.amount), 0)).filter(
            Expense.user_id == current_user.id,
            Expense.date >= period_start,
            Expense.date < next_period,
        )
        if budget.category_id is not None:
            query = query.filter(Expense.category_id == budget.category_id)
        spent = float(query.scalar() or 0)
    elif budget.category_id is None:
        spent = sum(spending_by_category.values())
    else:
        spent = spending_by_category.get(budget.category_id, 0.0)
    limit = float(budget.amount)
    percent_used = round((spent / limit) * 100, 2)
    progress_status = "over" if spent > limit else "near" if percent_used >= 80 else "under"
    return BudgetRead(
        id=budget.id,
        name=budget.name,
        amount=limit,
        period=budget.period,
        category_id=budget.category_id,
        category_name=budget.category.name if budget.category else "Overall",
        period_start=period_start,
        period_end=date.fromordinal(next_period.toordinal() - 1),
        spent=spent,
        remaining=round(limit - spent, 2),
        percent_used=percent_used,
        status=progress_status,
        created_at=budget.created_at,
        updated_at=budget.updated_at,
    )


def _validate_owned_category(category_id: int | None, current_user: CurrentUser, db: Session) -> None:
    if category_id is None:
        return
    category = db.query(ExpenseCategory.id).filter(
        ExpenseCategory.id == category_id,
        ExpenseCategory.user_id == current_user.id,
    ).first()
    if category is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found.")


@router.post("", response_model=BudgetRead, status_code=status.HTTP_201_CREATED)
async def create_budget(
    payload: BudgetCreate,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> BudgetRead:
    _validate_owned_category(payload.category_id, current_user, db)
    budget = Budget(
        user_id=current_user.id,
        name=payload.name,
        amount=payload.amount,
        period=payload.period,
        category_id=payload.category_id,
    )
    db.add(budget)
    db.commit()
    db.refresh(budget)
    return _budget_read(budget, db, current_user)


@router.get("", response_model=list[BudgetRead])
async def list_budgets(
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> list[BudgetRead]:
    budgets = (
        db.query(Budget)
        .options(joinedload(Budget.category))
        .filter(Budget.user_id == current_user.id)
        .order_by(Budget.id)
        .all()
    )
    if not budgets:
        return []

    period_start, next_period = _month_bounds()
    spending_by_category = {
        category_id: float(total)
        for category_id, total in db.query(Expense.category_id, func.sum(Expense.amount))
        .filter(
            Expense.user_id == current_user.id,
            Expense.date >= period_start,
            Expense.date < next_period,
        )
        .group_by(Expense.category_id)
        .all()
    }
    return [
        _budget_read(budget, db, current_user, spending_by_category=spending_by_category)
        for budget in budgets
    ]


@router.get("/{budget_id}", response_model=BudgetRead)
async def get_budget(
    budget_id: int,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> BudgetRead:
    budget = db.query(Budget).filter(Budget.id == budget_id, Budget.user_id == current_user.id).first()
    if budget is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Budget not found.")
    return _budget_read(budget, db, current_user)


@router.put("/{budget_id}", response_model=BudgetRead)
async def update_budget(
    budget_id: int,
    payload: BudgetUpdate,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> BudgetRead:
    budget = db.query(Budget).filter(Budget.id == budget_id, Budget.user_id == current_user.id).first()
    if budget is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Budget not found.")
    _validate_owned_category(payload.category_id, current_user, db)
    budget.name = payload.name
    budget.amount = payload.amount
    budget.period = payload.period
    budget.category_id = payload.category_id
    db.commit()
    db.refresh(budget)
    return _budget_read(budget, db, current_user)


@router.delete("/{budget_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_budget(
    budget_id: int,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> Response:
    budget = db.query(Budget).filter(Budget.id == budget_id, Budget.user_id == current_user.id).first()
    if budget is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Budget not found.")
    db.delete(budget)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
