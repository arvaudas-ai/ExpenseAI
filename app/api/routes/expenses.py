from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import asc, desc
from sqlalchemy.orm import Session, contains_eager

from app.api.dependencies import CurrentUser
from app.db.session import get_db
from app.models.category import ExpenseCategory
from app.models.expense import Expense
from app.schemas.expense import ExpenseCreate, ExpenseRead, ExpenseUpdate, VALID_PAYMENT_METHODS

router = APIRouter(prefix="/api/expenses", tags=["expenses"])


@router.post("", response_model=ExpenseRead, status_code=status.HTTP_201_CREATED)
async def create_expense(
    payload: ExpenseCreate,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> ExpenseRead:
    # Verify that the category belongs to the current user
    category = db.query(ExpenseCategory).filter(
        ExpenseCategory.id == payload.category_id,
        ExpenseCategory.user_id == current_user.id,
    ).first()
    if category is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found.")

    expense = Expense(
        user_id=current_user.id,
        category_id=payload.category_id,
        amount=payload.amount,
        description=payload.description.strip(),
        date=payload.date,
        payment_method=payload.payment_method.lower(),
    )
    db.add(expense)
    db.commit()
    db.refresh(expense)
    return ExpenseRead.model_validate(expense)


@router.get("", response_model=list[ExpenseRead])
async def list_expenses(
    current_user: CurrentUser,
    db: Session = Depends(get_db),
    search: Annotated[str | None, Query(max_length=100)] = None,
    start_date: date | None = None,
    end_date: date | None = None,
    category_id: int | None = Query(default=None, gt=0),
    payment_method: str | None = None,
    amount_min: float | None = Query(default=None, ge=0),
    amount_max: float | None = Query(default=None, gt=0),
    sort_by: Literal["date", "amount", "category", "created_at", "updated_at"] = "date",
    sort_order: Literal["asc", "desc"] = "desc",
    limit: int = Query(default=100, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> list[ExpenseRead]:
    """List current-user expenses with search, filters, sorting, and bounded pagination.

    Query parameters: search (description/category/payment text), start_date, end_date,
    category_id, payment_method, amount_min, amount_max, sort_by (date, amount,
    category, created_at, updated_at), sort_order (asc/desc), limit (1-100), and
    offset. Defaults are newest date first, limit 100, offset 0.
    """
    if start_date and end_date and start_date > end_date:
        raise HTTPException(status_code=422, detail="start_date must be on or before end_date.")
    if amount_min is not None and amount_max is not None and amount_min > amount_max:
        raise HTTPException(status_code=422, detail="amount_min must be less than or equal to amount_max.")
    normalized_payment_method = payment_method.strip().lower() if payment_method else None
    if normalized_payment_method and normalized_payment_method not in VALID_PAYMENT_METHODS:
        raise HTTPException(status_code=422, detail="payment_method is invalid.")

    query = (
        db.query(Expense)
        .options(contains_eager(Expense.category))
        .outerjoin(ExpenseCategory, Expense.category_id == ExpenseCategory.id)
        .filter(Expense.user_id == current_user.id)
    )
    if search and search.strip():
        escaped_search = search.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        search_pattern = f"%{escaped_search}%"
        query = query.filter(
            Expense.description.ilike(search_pattern, escape="\\")
            | Expense.payment_method.ilike(search_pattern, escape="\\")
            | ExpenseCategory.name.ilike(search_pattern, escape="\\")
        )
    if start_date:
        query = query.filter(Expense.date >= start_date)
    if end_date:
        query = query.filter(Expense.date <= end_date)
    if category_id is not None:
        query = query.filter(Expense.category_id == category_id)
    if normalized_payment_method:
        query = query.filter(Expense.payment_method == normalized_payment_method)
    if amount_min is not None:
        query = query.filter(Expense.amount >= amount_min)
    if amount_max is not None:
        query = query.filter(Expense.amount <= amount_max)

    sort_columns = {
        "date": Expense.date,
        "amount": Expense.amount,
        "category": ExpenseCategory.name,
        "created_at": Expense.created_at,
        "updated_at": Expense.updated_at,
    }
    sort_column = sort_columns[sort_by]
    order_column = asc(sort_column) if sort_order == "asc" else desc(sort_column)
    expenses = query.order_by(order_column, Expense.id.desc()).offset(offset).limit(limit).all()
    return [ExpenseRead.model_validate(expense) for expense in expenses]


@router.get("/{expense_id}", response_model=ExpenseRead)
async def get_expense(
    expense_id: int,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> ExpenseRead:
    expense = db.query(Expense).filter(Expense.id == expense_id, Expense.user_id == current_user.id).first()
    if expense is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Expense not found.")
    return ExpenseRead.model_validate(expense)


@router.put("/{expense_id}", response_model=ExpenseRead)
async def update_expense(
    expense_id: int,
    payload: ExpenseUpdate,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> ExpenseRead:
    expense = db.query(Expense).filter(Expense.id == expense_id, Expense.user_id == current_user.id).first()
    if expense is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Expense not found.")

    # If updating category, verify ownership
    if payload.category_id is not None:
        category = db.query(ExpenseCategory).filter(
            ExpenseCategory.id == payload.category_id,
            ExpenseCategory.user_id == current_user.id,
        ).first()
        if category is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found.")

    updates = payload.model_dump(exclude_none=True)
    if not updates:
        return ExpenseRead.model_validate(expense)

    for field, value in updates.items():
        if field == "description":
            setattr(expense, field, str(value).strip())
        elif field == "payment_method":
            setattr(expense, field, str(value).strip().lower())
        else:
            setattr(expense, field, value)

    db.add(expense)
    db.commit()
    db.refresh(expense)
    return ExpenseRead.model_validate(expense)


@router.delete("/{expense_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_expense(
    expense_id: int,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> None:
    expense = db.query(Expense).filter(Expense.id == expense_id, Expense.user_id == current_user.id).first()
    if expense is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Expense not found.")

    db.delete(expense)
    db.commit()
