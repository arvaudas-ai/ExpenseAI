from sqlalchemy import inspect, text

from app.db.base import Base
from app.db.session import engine

# Import models to register them with Base
from app.models.category import ExpenseCategory
from app.models.expense import Expense
from app.models.budget import Budget
from app.models.user import User


def create_database_tables() -> None:
    Base.metadata.create_all(bind=engine, checkfirst=True)
    migrate_legacy_expense_table()
    ensure_missing_indexes()
    ensure_user_profile_columns()


def migrate_legacy_expense_table() -> None:
    inspector = inspect(engine)
    if not inspector.has_table("expenses"):
        return

    columns = {column["name"] for column in inspector.get_columns("expenses")}
    if "category_id" in columns:
        return

    if "category" not in columns:
        return

    with engine.begin() as connection:
        connection.execute(text("DROP INDEX IF EXISTS ix_expenses_user_id_date"))
        connection.execute(text("DROP INDEX IF EXISTS ix_expenses_category_id"))
        connection.execute(text("ALTER TABLE expenses RENAME TO expenses_legacy"))

    try:
        Expense.__table__.create(bind=engine, checkfirst=True)

        with engine.begin() as connection:
            rows = connection.execute(
                text(
                    "SELECT id, user_id, category, amount, description, date, payment_method, created_at, updated_at FROM expenses_legacy"
                )
            ).fetchall()

            for row in rows:
                legacy_id, user_id, category_name, amount, description, expense_date, payment_method, created_at, updated_at = row
                category_id = connection.execute(
                    text(
                        "SELECT id FROM expense_categories WHERE user_id = :user_id AND name = :name LIMIT 1"
                    ),
                    {"user_id": user_id, "name": category_name},
                ).scalar()

                if category_id is None and category_name and str(category_name).strip():
                    connection.execute(
                        text(
                            "INSERT INTO expense_categories (user_id, name, icon, color, is_default, created_at, updated_at) "
                            "VALUES (:user_id, :name, 'other', '#95A5A6', 0, :created_at, :updated_at)"
                        ),
                        {
                            "user_id": user_id,
                            "name": str(category_name).strip(),
                            "created_at": created_at,
                            "updated_at": updated_at,
                        },
                    )
                    category_id = connection.execute(
                        text("SELECT id FROM expense_categories WHERE user_id = :user_id AND name = :name ORDER BY id DESC LIMIT 1"),
                        {"user_id": user_id, "name": str(category_name).strip()},
                    ).scalar()

                connection.execute(
                    text(
                        "INSERT INTO expenses (id, user_id, category_id, amount, description, date, payment_method, created_at, updated_at) "
                        "VALUES (:id, :user_id, :category_id, :amount, :description, :date, :payment_method, :created_at, :updated_at)"
                    ),
                    {
                        "id": legacy_id,
                        "user_id": user_id,
                        "category_id": category_id,
                        "amount": amount,
                        "description": description,
                        "date": expense_date,
                        "payment_method": payment_method,
                        "created_at": created_at,
                        "updated_at": updated_at,
                    },
                )

        with engine.begin() as connection:
            connection.execute(text("DROP TABLE expenses_legacy"))
    except Exception:
        with engine.begin() as connection:
            connection.execute(text("DROP TABLE IF EXISTS expenses_legacy"))
        raise


def ensure_missing_indexes() -> None:
    inspector = inspect(engine)

    if inspector.has_table("expense_categories"):
        existing_category_indexes = {index["name"] for index in inspector.get_indexes("expense_categories")}
        with engine.begin() as connection:
            if "ix_expense_categories_user_id" not in existing_category_indexes:
                connection.execute(text("CREATE INDEX IF NOT EXISTS ix_expense_categories_user_id ON expense_categories (user_id)"))
            if "ix_expense_categories_user_id_name" not in existing_category_indexes:
                connection.execute(text("CREATE INDEX IF NOT EXISTS ix_expense_categories_user_id_name ON expense_categories (user_id, name)"))

    if inspector.has_table("expenses"):
        existing_expense_indexes = {index["name"] for index in inspector.get_indexes("expenses")}
        with engine.begin() as connection:
            if "ix_expenses_user_id_date" not in existing_expense_indexes:
                connection.execute(text("CREATE INDEX IF NOT EXISTS ix_expenses_user_id_date ON expenses (user_id, date)"))
            if "ix_expenses_user_id_amount" not in existing_expense_indexes:
                connection.execute(text("CREATE INDEX IF NOT EXISTS ix_expenses_user_id_amount ON expenses (user_id, amount)"))
            if "ix_expenses_category_id" not in existing_expense_indexes:
                connection.execute(text("CREATE INDEX IF NOT EXISTS ix_expenses_category_id ON expenses (category_id)"))

    if inspector.has_table("budgets"):
        existing_budget_indexes = {index["name"] for index in inspector.get_indexes("budgets")}
        if "ix_budgets_category_id" not in existing_budget_indexes:
            with engine.begin() as connection:
                connection.execute(text("CREATE INDEX IF NOT EXISTS ix_budgets_category_id ON budgets (category_id)"))


def ensure_user_profile_columns() -> None:
    inspector = inspect(engine)
    if not inspector.has_table("users"):
        return

    columns = {column["name"] for column in inspector.get_columns("users")}

    with engine.begin() as connection:
        if "currency" not in columns:
            connection.execute(text("ALTER TABLE users ADD COLUMN currency VARCHAR(10) NOT NULL DEFAULT 'USD'"))
        if "preferences" not in columns:
            connection.execute(text("ALTER TABLE users ADD COLUMN preferences VARCHAR(500) NOT NULL DEFAULT '{}'"))

        connection.execute(text("UPDATE users SET currency = 'USD' WHERE currency IS NULL OR TRIM(currency) = ''"))
        connection.execute(text("UPDATE users SET preferences = '{}' WHERE preferences IS NULL OR TRIM(preferences) = ''"))
