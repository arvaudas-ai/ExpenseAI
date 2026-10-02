import hashlib
import hmac
import os

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentUser, create_access_token
from app.db.session import get_db
from app.models.category import ExpenseCategory
from app.models.user import User
from app.schemas.user import TokenResponse, UserCreate, UserLogin, UserRead

router = APIRouter(prefix="/api/auth", tags=["auth"])


def hash_password(password: str) -> str:
    salt = hashlib.sha256(os.urandom(60)).hexdigest().encode("ascii")
    derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 200000)
    return f"pbkdf2_sha256$200000${salt.decode('ascii')}${derived.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        algorithm, iterations, salt, expected_hash = stored_hash.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("ascii"), int(iterations))
        return hmac.compare_digest(derived.hex(), expected_hash)
    except (ValueError, TypeError):
        return False

# Default categories for new users
DEFAULT_CATEGORIES = [
    {"name": "Food & Dining", "icon": "food", "color": "#FF8A65"},
    {"name": "Transportation", "icon": "transport", "color": "#4D96FF"},
    {"name": "Utilities", "icon": "utilities", "color": "#FFD93D"},
    {"name": "Entertainment", "icon": "entertainment", "color": "#E91E63"},
    {"name": "Shopping", "icon": "shopping", "color": "#9B59B6"},
    {"name": "Health & Medical", "icon": "health", "color": "#FF6B6B"},
    {"name": "Education", "icon": "education", "color": "#3498DB"},
    {"name": "Travel", "icon": "travel", "color": "#2ECC71"},
]


def create_default_categories(user_id: int, db: Session) -> None:
    """Create default expense categories for a new user."""
    for category_data in DEFAULT_CATEGORIES:
        category = ExpenseCategory(
            user_id=user_id,
            name=category_data["name"],
            icon=category_data["icon"],
            color=category_data["color"],
            is_default=True,
        )
        db.add(category)
    db.commit()


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def register_user(payload: UserCreate, db: Session = Depends(get_db)) -> UserRead:
    if not payload.name or not payload.name.strip():
        raise HTTPException(status_code=400, detail="Full name is required.")

    if not payload.email or not str(payload.email).strip():
        raise HTTPException(status_code=400, detail="Email is required.")

    if not payload.password or not payload.password.strip():
        raise HTTPException(status_code=400, detail="Password is required.")

    if not payload.password_confirmation or not payload.password_confirmation.strip():
        raise HTTPException(status_code=400, detail="Password confirmation is required.")

    if payload.password != payload.password_confirmation:
        raise HTTPException(status_code=400, detail="Passwords do not match.")

    if len(payload.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters long.")

    normalized_email = str(payload.email).strip().lower()
    existing_user = db.query(User).filter(User.email == normalized_email).first()
    if existing_user:
        raise HTTPException(status_code=409, detail="An account with this email already exists.")

    hashed_password = hash_password(payload.password)

    user = User(
        name=payload.name.strip(),
        email=normalized_email,
        password_hash=hashed_password,
    )

    try:
        db.add(user)
        db.commit()
        db.refresh(user)
        create_default_categories(user.id, db)
        db.refresh(user)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="An account with this email already exists.") from exc
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail="Unable to create user account. Please try again.") from exc

    return UserRead.model_validate(user)


@router.post("/login", response_model=TokenResponse)
async def login_user(payload: UserLogin, db: Session = Depends(get_db)) -> TokenResponse:
    if not payload.email or not str(payload.email).strip():
        raise HTTPException(status_code=400, detail="Email is required.")

    if not payload.password or not payload.password.strip():
        raise HTTPException(status_code=400, detail="Password is required.")

    email = str(payload.email).strip().lower()
    user = db.query(User).filter(User.email == email).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password.")

    access_token = create_access_token(user.id)
    return TokenResponse(access_token=access_token, user=UserRead.model_validate(user))


@router.get("/me", response_model=UserRead)
async def get_current_user_profile(current_user: CurrentUser) -> UserRead:
    return UserRead.model_validate(current_user)


@router.post("/logout")
async def logout_user(current_user: CurrentUser) -> dict[str, str]:
    return {"message": "Logout successful."}
