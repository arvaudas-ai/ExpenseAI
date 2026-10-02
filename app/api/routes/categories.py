from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentUser
from app.db.session import get_db
from app.models.budget import Budget
from app.models.category import ExpenseCategory
from app.schemas.category import ExpenseCategoryCreate, ExpenseCategoryRead, ExpenseCategoryUpdate

router = APIRouter(prefix="/api/categories", tags=["categories"])


@router.post("", response_model=ExpenseCategoryRead, status_code=status.HTTP_201_CREATED)
async def create_category(
    payload: ExpenseCategoryCreate,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> ExpenseCategoryRead:
    """Create a new custom expense category for the current user."""
    category = ExpenseCategory(
        user_id=current_user.id,
        name=payload.name,
        icon=payload.icon,
        color=payload.color,
        is_default=False,
    )
    db.add(category)
    db.commit()
    db.refresh(category)
    return ExpenseCategoryRead.model_validate(category)


@router.get("", response_model=list[ExpenseCategoryRead])
async def list_categories(
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> list[ExpenseCategoryRead]:
    """List all expense categories for the current user (custom + defaults)."""
    categories = db.query(ExpenseCategory).filter(ExpenseCategory.user_id == current_user.id).order_by(ExpenseCategory.name).all()
    return [ExpenseCategoryRead.model_validate(category) for category in categories]


@router.get("/{category_id}", response_model=ExpenseCategoryRead)
async def get_category(
    category_id: int,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> ExpenseCategoryRead:
    """Get a specific category by ID (ownership verified)."""
    category = db.query(ExpenseCategory).filter(
        ExpenseCategory.id == category_id,
        ExpenseCategory.user_id == current_user.id,
    ).first()
    if category is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found.")
    return ExpenseCategoryRead.model_validate(category)


@router.put("/{category_id}", response_model=ExpenseCategoryRead)
async def update_category(
    category_id: int,
    payload: ExpenseCategoryUpdate,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> ExpenseCategoryRead:
    """Update a custom expense category (cannot modify default categories)."""
    category = db.query(ExpenseCategory).filter(
        ExpenseCategory.id == category_id,
        ExpenseCategory.user_id == current_user.id,
    ).first()
    if category is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found.")

    if category.is_default:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot modify default categories.")

    updates = payload.model_dump(exclude_none=True)
    if not updates:
        return ExpenseCategoryRead.model_validate(category)

    for field, value in updates.items():
        setattr(category, field, value)

    db.add(category)
    db.commit()
    db.refresh(category)
    return ExpenseCategoryRead.model_validate(category)


@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_category(
    category_id: int,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> None:
    """Delete a custom category (cannot delete default categories)."""
    category = db.query(ExpenseCategory).filter(
        ExpenseCategory.id == category_id,
        ExpenseCategory.user_id == current_user.id,
    ).first()
    if category is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found.")

    if category.is_default:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot delete default categories.")

    if db.query(Budget.id).filter(Budget.category_id == category_id, Budget.user_id == current_user.id).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Delete budgets using this category before deleting the category.",
        )

    db.delete(category)
    db.commit()
