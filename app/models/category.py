from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

# Valid icon set - safe, predefined icons only
VALID_ICONS = {
    "food",
    "transport",
    "utilities",
    "entertainment",
    "shopping",
    "health",
    "education",
    "travel",
    "dining",
    "groceries",
    "gas",
    "electricity",
    "water",
    "internet",
    "phone",
    "movie",
    "music",
    "books",
    "sports",
    "gym",
    "medical",
    "pharmacy",
    "doctor",
    "school",
    "tuition",
    "plane",
    "hotel",
    "taxi",
    "other",
}

# Valid color set - safe, predefined colors only
VALID_COLORS = {
    "#FF6B6B",  # red
    "#FF8A65",  # orange
    "#FFD93D",  # yellow
    "#6BCB77",  # green
    "#4D96FF",  # blue
    "#9B59B6",  # purple
    "#E74C3C",  # dark red
    "#3498DB",  # bright blue
    "#2ECC71",  # bright green
    "#E91E63",  # pink
    "#00BCD4",  # cyan
    "#795548",  # brown
}


class ExpenseCategory(Base):
    __tablename__ = "expense_categories"

    __table_args__ = (
        Index("ix_expense_categories_user_id", "user_id"),
        Index("ix_expense_categories_user_id_name", "user_id", "name"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    icon: Mapped[str] = mapped_column(String(50), nullable=False, default="other")
    color: Mapped[str] = mapped_column(String(10), nullable=False, default="#95A5A6")
    is_default: Mapped[bool] = mapped_column(nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    user: Mapped["User"] = relationship("User", back_populates="expense_categories")
