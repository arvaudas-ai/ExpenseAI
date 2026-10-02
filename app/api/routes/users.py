import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentUser
from app.api.routes.auth import hash_password, verify_password
from app.db.session import get_db
from app.models.user import User
from app.schemas.user import PasswordChangeRequest, UserRead, UserUpdate

router = APIRouter(prefix="/api/users", tags=["users"])


def _preferences_to_dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        if isinstance(parsed, dict):
            return parsed
        return {}
    if isinstance(value, dict):
        return value
    return {}


@router.get("/me", response_model=UserRead)
async def get_current_user_profile(current_user: CurrentUser) -> UserRead:
    return UserRead.model_validate(current_user)


@router.put("/me", response_model=UserRead)
async def update_current_user_profile(
    payload: UserUpdate,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> UserRead:
    updates = payload.model_dump(exclude_none=True)
    if not updates:
        return UserRead.model_validate(current_user)

    if "email" in updates:
        normalized_email = str(updates["email"]).strip().lower()
        existing_user = db.query(User).filter(User.email == normalized_email, User.id != current_user.id).first()
        if existing_user:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An account with this email already exists.")
        current_user.email = normalized_email

    if "name" in updates:
        current_user.name = str(updates["name"]).strip()

    if "currency" in updates:
        current_user.currency = str(updates["currency"]).strip().upper() or "USD"

    if "preferences" in updates:
        preferences = _preferences_to_dict(updates["preferences"])
        current_user.preferences = json.dumps(preferences)

    db.add(current_user)
    db.commit()
    db.refresh(current_user)

    return UserRead.model_validate(current_user)


@router.put("/me/password")
async def change_current_user_password(
    payload: PasswordChangeRequest,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> dict[str, str]:
    if not verify_password(payload.current_password, current_user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Current password is incorrect.")

    if payload.new_password != payload.confirm_new_password:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="New passwords do not match.")

    if len(payload.new_password) < 8:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="New password must be at least 8 characters long.")

    if payload.new_password == payload.current_password:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="New password must be different from the current password.")

    current_user.password_hash = hash_password(payload.new_password)
    db.add(current_user)
    db.commit()

    return {"message": "Password updated successfully."}
