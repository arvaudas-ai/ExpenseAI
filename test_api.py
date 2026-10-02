from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta, timezone
from typing import Iterator

import httpx
import pytest
import jwt
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine, event, inspect
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db
from app.core.config import Settings, get_settings
from app.main import app
from app.api.routes import analysis as analysis_routes
from app.services import providers
from app.services.ai_rate_limit import AIRequestLimiter


TEST_ENGINE = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)


@event.listens_for(TEST_ENGINE, "connect")
def enable_test_foreign_keys(dbapi_connection: object, connection_record: object) -> None:
    dbapi_connection.execute("PRAGMA foreign_keys=ON")


class ApiClient:
    def __init__(self) -> None:
        self.loop = asyncio.new_event_loop()
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        )

    def request(self, method: str, path: str, **kwargs: object) -> httpx.Response:
        return self.loop.run_until_complete(self.client.request(method, path, **kwargs))

    def close(self) -> None:
        self.loop.run_until_complete(self.client.aclose())
        self.loop.close()

    def get(self, path: str, **kwargs: object) -> httpx.Response:
        return self.request("GET", path, **kwargs)

    def post(self, path: str, **kwargs: object) -> httpx.Response:
        return self.request("POST", path, **kwargs)

    def put(self, path: str, **kwargs: object) -> httpx.Response:
        return self.request("PUT", path, **kwargs)

    def delete(self, path: str, **kwargs: object) -> httpx.Response:
        return self.request("DELETE", path, **kwargs)


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[ApiClient]:
    Base.metadata.create_all(bind=TEST_ENGINE)

    def override_get_db() -> Iterator[Session]:
        with Session(TEST_ENGINE) as session:
            yield session

    monkeypatch.setattr("app.main.create_database_tables", lambda: None)
    app.dependency_overrides[get_db] = override_get_db

    client = ApiClient()
    yield client
    client.close()

    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=TEST_ENGINE)


def register(client: ApiClient, email: str, name: str = "Test User") -> dict:
    response = client.post(
        "/api/auth/register",
        json={
            "name": name,
            "email": email,
            "password": "Password123",
            "password_confirmation": "Password123",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def login(client: ApiClient, email: str) -> str:
    response = client.post("/api/auth/login", json={"email": email, "password": "Password123"})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def count_sql_queries(callback) -> tuple[httpx.Response, int]:
    statements: list[str] = []

    def record_statement(connection, cursor, statement, parameters, context, executemany) -> None:
        statements.append(statement)

    event.listen(TEST_ENGINE, "before_cursor_execute", record_statement)
    try:
        response = callback()
    finally:
        event.remove(TEST_ENGINE, "before_cursor_execute", record_statement)
    return response, len(statements)


def create_custom_category(client: ApiClient, token: str, name: str = "Coffee") -> dict:
    response = client.post(
        "/api/categories",
        headers=auth(token),
        json={"name": name, "icon": "dining", "color": "#FF8A65"},
    )
    assert response.status_code == 201, response.text
    return response.json()


def create_expense(client: ApiClient, token: str, category_id: int, **overrides: object) -> dict:
    payload = {
        "category_id": category_id,
        "amount": 25.50,
        "description": "Test expense",
        "date": date.today().isoformat(),
        "payment_method": "cash",
    }
    payload.update(overrides)
    response = client.post("/api/expenses", headers=auth(token), json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def test_registration_login_and_authentication(client: ApiClient) -> None:
    user = register(client, "Alice@Example.com", "Alice")

    assert user["email"] == "alice@example.com"
    assert "password" not in user
    assert "password_hash" not in user

    token = login(client, "ALICE@example.com")
    profile = client.get("/api/auth/me", headers=auth(token))
    assert profile.status_code == 200
    assert profile.json()["name"] == "Alice"

    duplicate = client.post(
        "/api/auth/register",
        json={
            "name": "Another Alice",
            "email": "alice@example.com",
            "password": "Password123",
            "password_confirmation": "Password123",
        },
    )
    assert duplicate.status_code == 409

    invalid_login = client.post(
        "/api/auth/login",
        json={"email": "alice@example.com", "password": "wrong-password"},
    )
    assert invalid_login.status_code == 401


def test_protected_routes_require_valid_authentication(client: ApiClient) -> None:
    protected_requests = [
        client.get("/api/auth/me"),
        client.get("/api/users/me"),
        client.get("/api/categories"),
        client.get("/api/expenses"),
        client.get("/api/dashboard/summary"),
    ]

    assert [response.status_code for response in protected_requests] == [401] * len(protected_requests)
    assert client.post("/api/auth/logout").status_code == 401

    invalid_token = {"Authorization": "Bearer not-a-real-token"}
    assert client.get("/api/dashboard/summary", headers=invalid_token).status_code == 401

    malformed_subject = jwt.encode(
        {"sub": "not-an-integer"},
        get_settings().jwt_secret_key,
        algorithm="HS256",
    )
    assert client.get(
        "/api/dashboard/summary",
        headers=auth(malformed_subject),
    ).status_code == 401

    invalid_claims = [
        {
            "sub": "1",
            "iat": datetime.now(timezone.utc),
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
            "iss": "wrong-issuer",
        },
        {
            "sub": "0",
            "iat": datetime.now(timezone.utc),
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
            "iss": get_settings().app_name,
        },
        {
            "iat": datetime.now(timezone.utc),
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
            "iss": get_settings().app_name,
        },
    ]
    for claims in invalid_claims:
        bad_claim_token = jwt.encode(claims, get_settings().jwt_secret_key, algorithm="HS256")
        assert client.get("/api/dashboard/summary", headers=auth(bad_claim_token)).status_code == 401

        wrong_subject_type = jwt.encode(
            {
                "sub": "1.5",
                "iat": datetime.now(timezone.utc),
                "exp": datetime.now(timezone.utc) + timedelta(hours=1),
                "iss": get_settings().app_name,
            },
            get_settings().jwt_secret_key,
            algorithm="HS256",
        )
        assert client.get("/api/dashboard/summary", headers=auth(wrong_subject_type)).status_code == 401

    expired_token = jwt.encode(
        {
            "sub": "1",
            "iat": datetime.now(timezone.utc) - timedelta(hours=2),
            "exp": datetime.now(timezone.utc) - timedelta(hours=1),
            "iss": get_settings().app_name,
        },
        get_settings().jwt_secret_key,
        algorithm="HS256",
    )
    assert client.get("/api/dashboard/summary", headers=auth(expired_token)).status_code == 401

    missing_claim = jwt.encode(
        {"sub": "1", "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
        get_settings().jwt_secret_key,
        algorithm="HS256",
    )
    assert client.get("/api/dashboard/summary", headers=auth(missing_claim)).status_code == 401


def test_malformed_json_and_invalid_expense_date_return_422(client: ApiClient) -> None:
    register(client, "malformed-json@example.com")
    token = login(client, "malformed-json@example.com")
    headers = {**auth(token), "Content-Type": "application/json"}

    malformed_expense = client.post("/api/expenses", headers=headers, content='{"amount":')
    malformed_chat = client.post("/api/assistant/chat", headers=headers, content='{"message":')
    invalid_date = client.get("/api/expenses?start_date=not-a-date", headers=auth(token))

    assert malformed_expense.status_code == 422
    assert malformed_chat.status_code == 422
    assert invalid_date.status_code == 422
    assert "input" not in malformed_expense.text
    assert "input" not in malformed_chat.text


def test_new_account_empty_state_across_private_data_endpoints(client: ApiClient) -> None:
    register(client, "empty-account@example.com")
    token = login(client, "empty-account@example.com")
    headers = auth(token)

    expenses = client.get("/api/expenses", headers=headers)
    budgets = client.get("/api/budgets", headers=headers)
    dashboard = client.get("/api/dashboard/summary", headers=headers)
    export = client.get("/api/dashboard/export.csv", headers=headers)
    analysis = client.get("/api/analysis/spending", headers=headers)

    assert expenses.status_code == 200 and expenses.json() == []
    assert budgets.status_code == 200 and budgets.json() == []
    assert dashboard.status_code == 200
    assert dashboard.json()["total_spending"] == 0
    assert dashboard.json()["expense_count"] == 0
    assert dashboard.json()["spending_by_category"] == []
    assert all(month["total"] == 0 for month in dashboard.json()["monthly_spending"])
    assert export.status_code == 200
    assert export.text.startswith("date,description,category,amount,currency,payment_method")
    assert analysis.status_code == 200
    assert analysis.json()["insufficient_data"] is True


def test_security_headers_are_present_on_public_responses(client: ApiClient) -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "strict-origin-when-cross-origin"
    assert response.headers["permissions-policy"] == "camera=(), microphone=(), geolocation=()"


def test_static_assets_and_pages_are_served(client: ApiClient) -> None:
    page = client.get("/login")
    stylesheet = client.get("/static/css/styles.css")
    categories_script = client.get("/static/js/categories.js")
    expenses_script = client.get("/static/js/expenses.js")
    dashboard_script = client.get("/static/js/dashboard.js")

    assert page.status_code == 200
    assert "Sign in" in page.text
    assert stylesheet.status_code == 200
    assert "--accent" in stylesheet.text
    assert "escapeHtml(category.name)" in categories_script.text
    assert "categoriesList.textContent = `Error loading categories: ${error.message}`" in categories_script.text
    assert "escapeHtml(categoryName)" in expenses_script.text
    assert "escapeHtml(expense.description)" in expenses_script.text
    assert "escapeHtml(category.name)" in dashboard_script.text


def test_user_isolation_for_categories_and_expenses(client: ApiClient) -> None:
    register(client, "alice@example.com", "Alice")
    register(client, "bob@example.com", "Bob")
    alice_token = login(client, "alice@example.com")
    bob_token = login(client, "bob@example.com")

    alice_category = create_custom_category(client, alice_token, "Alice Only")
    bob_categories = client.get("/api/categories", headers=auth(bob_token))
    assert bob_categories.status_code == 200
    assert alice_category["id"] not in {category["id"] for category in bob_categories.json()}

    assert client.get(f"/api/categories/{alice_category['id']}", headers=auth(bob_token)).status_code == 404
    assert client.put(
        f"/api/categories/{alice_category['id']}",
        headers=auth(bob_token),
        json={"name": "Hijacked"},
    ).status_code == 404
    assert client.delete(f"/api/categories/{alice_category['id']}", headers=auth(bob_token)).status_code == 404

    alice_expense = create_expense(client, alice_token, alice_category["id"])
    assert client.get("/api/expenses", headers=auth(bob_token)).json() == []
    assert client.get(f"/api/expenses/{alice_expense['id']}", headers=auth(bob_token)).status_code == 404
    assert client.put(
        f"/api/expenses/{alice_expense['id']}",
        headers=auth(bob_token),
        json={"amount": 999},
    ).status_code == 404
    assert client.delete(f"/api/expenses/{alice_expense['id']}", headers=auth(bob_token)).status_code == 404

    bob_category = create_custom_category(client, bob_token, "Bob Only")
    cross_user_expense = client.post(
        "/api/expenses",
        headers=auth(alice_token),
        json={
            "category_id": bob_category["id"],
            "amount": 10,
            "description": "Cross user",
            "date": date.today().isoformat(),
            "payment_method": "cash",
        },
    )
    assert cross_user_expense.status_code == 404


def test_expense_crud_and_category_response(client: ApiClient) -> None:
    register(client, "expense@example.com")
    token = login(client, "expense@example.com")
    category = create_custom_category(client, token)

    expense = create_expense(client, token, category["id"], amount=40, description="Original")
    assert expense["category"]["id"] == category["id"]
    assert expense["category"]["name"] == "Coffee"

    listed = client.get("/api/expenses", headers=auth(token))
    assert listed.status_code == 200
    assert listed.json()[0]["id"] == expense["id"]

    updated = client.put(
        f"/api/expenses/{expense['id']}",
        headers=auth(token),
        json={"amount": 55.25, "description": "Updated"},
    )
    assert updated.status_code == 200
    assert updated.json()["amount"] == 55.25
    assert updated.json()["description"] == "Updated"

    deleted = client.delete(f"/api/expenses/{expense['id']}", headers=auth(token))
    assert deleted.status_code == 204
    assert client.get(f"/api/expenses/{expense['id']}", headers=auth(token)).status_code == 404


def test_expense_search_filters_sorting_pagination_and_user_isolation(client: ApiClient) -> None:
    register(client, "list-alice@example.com", "Alice")
    register(client, "list-bob@example.com", "Bob")
    alice_token = login(client, "list-alice@example.com")
    bob_token = login(client, "list-bob@example.com")
    alice_food = create_custom_category(client, alice_token, "Dining & Food")
    alice_travel = create_custom_category(client, alice_token, "Travel")
    bob_category = create_custom_category(client, bob_token, "Private Dining")

    create_expense(client, alice_token, alice_food["id"], amount=25, description="Cafe sandwich", date="2026-04-01", payment_method="credit_card")
    create_expense(client, alice_token, alice_food["id"], amount=75, description="Market groceries", date="2026-04-03", payment_method="cash")
    create_expense(client, alice_token, alice_travel["id"], amount=150, description="Train fare", date="2026-04-02", payment_method="debit_card")
    create_expense(client, bob_token, bob_category["id"], amount=999, description="Private Cafe", date="2026-04-04", payment_method="cash")

    default_list = client.get("/api/expenses", headers=auth(alice_token))
    assert default_list.status_code == 200
    assert [expense["description"] for expense in default_list.json()] == ["Market groceries", "Train fare", "Cafe sandwich"]

    combined = client.get(
        "/api/expenses?search=dining&start_date=2026-04-01&end_date=2026-04-03&category_id="
        f"{alice_food['id']}&payment_method=cash&amount_min=50&amount_max=100&sort_by=amount&sort_order=asc",
        headers=auth(alice_token),
    )
    assert combined.status_code == 200
    assert [expense["description"] for expense in combined.json()] == ["Market groceries"]

    category_search = client.get("/api/expenses?search=travel", headers=auth(alice_token))
    payment_search = client.get("/api/expenses?search=credit_card", headers=auth(alice_token))
    assert [item["description"] for item in category_search.json()] == ["Train fare"]
    assert [item["description"] for item in payment_search.json()] == ["Cafe sandwich"]

    amount_desc = client.get("/api/expenses?sort_by=amount&sort_order=desc", headers=auth(alice_token))
    assert [item["amount"] for item in amount_desc.json()] == [150, 75, 25]
    category_sort = client.get("/api/expenses?sort_by=category&sort_order=asc", headers=auth(alice_token))
    assert [item["category"]["name"] for item in category_sort.json()] == ["Dining & Food", "Dining & Food", "Travel"]

    first_page = client.get("/api/expenses?limit=2&offset=0", headers=auth(alice_token))
    second_page = client.get("/api/expenses?limit=2&offset=2", headers=auth(alice_token))
    assert len(first_page.json()) == 2
    assert len(second_page.json()) == 1
    assert not any("Private" in str(item) for item in first_page.json() + second_page.json())
    assert client.get("/api/expenses?search=Private", headers=auth(alice_token)).json() == []

    assert client.get("/api/expenses?sort_by=unknown", headers=auth(alice_token)).status_code == 422
    assert client.get("/api/expenses?sort_order=sideways", headers=auth(alice_token)).status_code == 422
    assert client.get("/api/expenses?limit=101", headers=auth(alice_token)).status_code == 422
    assert client.get("/api/expenses?amount_min=100&amount_max=10", headers=auth(alice_token)).status_code == 422
    assert client.get("/api/expenses?payment_method=crypto", headers=auth(alice_token)).status_code == 422
    assert client.get("/api/expenses?start_date=2026-04-05&end_date=2026-04-01", headers=auth(alice_token)).status_code == 422


def test_category_crud_and_default_protection(client: ApiClient) -> None:
    register(client, "category@example.com")
    token = login(client, "category@example.com")

    categories = client.get("/api/categories", headers=auth(token))
    assert categories.status_code == 200
    assert len(categories.json()) == 8
    default_category = categories.json()[0]

    assert client.put(
        f"/api/categories/{default_category['id']}",
        headers=auth(token),
        json={"name": "Changed Default"},
    ).status_code == 403
    assert client.delete(f"/api/categories/{default_category['id']}", headers=auth(token)).status_code == 403

    category = create_custom_category(client, token)
    fetched = client.get(f"/api/categories/{category['id']}", headers=auth(token))
    assert fetched.status_code == 200

    updated = client.put(
        f"/api/categories/{category['id']}",
        headers=auth(token),
        json={"name": "Updated Coffee", "icon": "books", "color": "#4D96FF"},
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "Updated Coffee"

    assert client.delete(f"/api/categories/{category['id']}", headers=auth(token)).status_code == 204
    assert client.get(f"/api/categories/{category['id']}", headers=auth(token)).status_code == 404


def test_deleting_custom_category_preserves_expense_as_uncategorized(client: ApiClient) -> None:
    register(client, "category-delete-expense@example.com")
    token = login(client, "category-delete-expense@example.com")
    category = create_custom_category(client, token, "Temporary category")
    expense = create_expense(client, token, category["id"], description="Retained transaction")

    deleted = client.delete(f"/api/categories/{category['id']}", headers=auth(token))
    retained = client.get(f"/api/expenses/{expense['id']}", headers=auth(token))

    assert deleted.status_code == 204
    assert retained.status_code == 200
    assert retained.json()["category_id"] is None
    assert retained.json()["category"] is None


def test_dashboard_calculations_are_user_specific(client: ApiClient) -> None:
    register(client, "dashboard@example.com")
    register(client, "other@example.com")
    token = login(client, "dashboard@example.com")
    other_token = login(client, "other@example.com")
    category = create_custom_category(client, token, "Dashboard Food")
    other_category = create_custom_category(client, other_token, "Other Food")

    today = date.today()
    previous_month = today.replace(day=1) - timedelta(days=1)
    create_expense(client, token, category["id"], amount=10, description="Today", date=today.isoformat())
    create_expense(client, token, category["id"], amount=20, description="Previous month", date=previous_month.isoformat())
    create_expense(client, token, category["id"], amount=7, description="Old", date="2020-01-15")
    create_expense(client, other_token, other_category["id"], amount=999, description="Private")

    response = client.get("/api/dashboard/summary", headers=auth(token))
    assert response.status_code == 200
    summary = response.json()

    assert summary["total_spending"] == 37
    assert summary["expense_count"] == 3
    assert summary["spending_by_category"][0]["name"] == "Dashboard Food"
    assert summary["spending_by_category"][0]["total"] == 37
    assert len(summary["recent_expenses"]) == 3
    assert {expense["description"] for expense in summary["recent_expenses"]} == {"Today", "Previous month", "Old"}

    monthly = {month["month"]: month for month in summary["monthly_spending"]}
    assert monthly[today.strftime("%Y-%m")]["total"] == 10
    assert monthly[previous_month.strftime("%Y-%m")]["total"] == 20
    assert all(month["total"] == 0 for key, month in monthly.items() if key not in {today.strftime("%Y-%m"), previous_month.strftime("%Y-%m")})
    assert response.json()["payment_method_spending"] == [{"payment_method": "cash", "total": 37, "expense_count": 3}]


def test_list_analytics_chat_and_budget_queries_do_not_scale_per_row(
    client: ApiClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    register(client, "query-count@example.com")
    token = login(client, "query-count@example.com")
    categories = [create_custom_category(client, token, f"Query category {index}") for index in range(4)]
    for index, category in enumerate(categories):
        create_expense(
            client,
            token,
            category["id"],
            amount=10 + index,
            description=f"Query expense {index}",
            date=date.today().isoformat(),
        )
        client.post(
            "/api/budgets",
            headers=auth(token),
            json={"name": f"Budget {index}", "amount": 100, "category_id": category["id"]},
        )
    client.post("/api/budgets", headers=auth(token), json={"name": "Overall", "amount": 250})

    expenses, expense_query_count = count_sql_queries(lambda: client.get("/api/expenses", headers=auth(token)))
    dashboard, dashboard_query_count = count_sql_queries(lambda: client.get("/api/dashboard/summary", headers=auth(token)))
    export, export_query_count = count_sql_queries(lambda: client.get("/api/dashboard/export.csv", headers=auth(token)))
    chat, chat_query_count = count_sql_queries(
        lambda: client.post("/api/assistant/chat", headers=auth(token), json={"message": "Give me a summary"})
    )
    budgets, budget_query_count = count_sql_queries(lambda: client.get("/api/budgets", headers=auth(token)))

    assert expenses.status_code == dashboard.status_code == export.status_code == chat.status_code == budgets.status_code == 200
    assert len(expenses.json()) == 4
    assert len(budgets.json()) == 5
    assert expense_query_count <= 2
    assert dashboard_query_count <= 2
    assert export_query_count <= 2
    assert chat_query_count <= 2
    assert budget_query_count <= 3
    expense_indexes = {index["name"] for index in inspect(TEST_ENGINE).get_indexes("expenses")}
    budget_indexes = {index["name"] for index in inspect(TEST_ENGINE).get_indexes("budgets")}
    assert "ix_expenses_user_id_amount" in expense_indexes
    assert "ix_budgets_category_id" in budget_indexes

    with TEST_ENGINE.begin() as connection:
        connection.exec_driver_sql("DROP INDEX ix_expenses_user_id_amount")
        connection.exec_driver_sql("DROP INDEX ix_budgets_category_id")
    monkeypatch.setattr("app.db.init_db.engine", TEST_ENGINE)
    from app.db.init_db import ensure_missing_indexes

    ensure_missing_indexes()
    repaired_expense_indexes = {index["name"] for index in inspect(TEST_ENGINE).get_indexes("expenses")}
    repaired_budget_indexes = {index["name"] for index in inspect(TEST_ENGINE).get_indexes("budgets")}
    assert "ix_expenses_user_id_amount" in repaired_expense_indexes
    assert "ix_budgets_category_id" in repaired_budget_indexes


def test_validation_and_error_handling(client: ApiClient) -> None:
    register(client, "validation@example.com")
    token = login(client, "validation@example.com")
    category = create_custom_category(client, token)

    invalid_expense = client.post(
        "/api/expenses",
        headers=auth(token),
        json={
            "category_id": category["id"],
            "amount": 0,
            "description": "Invalid",
            "date": date.today().isoformat(),
            "payment_method": "cash",
        },
    )
    assert invalid_expense.status_code == 422

    invalid_nan_amount = client.post(
        "/api/expenses",
        headers={**auth(token), "Content-Type": "application/json"},
        content=(
            '{"category_id":%d,"amount":NaN,"description":"Invalid NaN",'
            '"date":"%s","payment_method":"cash"}'
        ) % (category["id"], date.today().isoformat()),
    )
    invalid_large_amount = client.post(
        "/api/expenses",
        headers=auth(token),
        json={
            "category_id": category["id"],
            "amount": 100000000,
            "description": "Too large",
            "date": date.today().isoformat(),
            "payment_method": "cash",
        },
    )
    assert invalid_nan_amount.status_code == 422
    assert all("input" not in error for error in invalid_nan_amount.json()["detail"])
    assert invalid_large_amount.status_code == 422

    invalid_payment = client.post(
        "/api/expenses",
        headers=auth(token),
        json={
            "category_id": category["id"],
            "amount": 10,
            "description": "Invalid payment",
            "date": date.today().isoformat(),
            "payment_method": "crypto",
        },
    )
    assert invalid_payment.status_code == 422

    invalid_category = client.post(
        "/api/categories",
        headers=auth(token),
        json={"name": "Bad<script>", "icon": "dining", "color": "#FF8A65"},
    )
    assert invalid_category.status_code == 422

    missing_expense = client.get("/api/expenses/999999", headers=auth(token))
    assert missing_expense.status_code == 404


def test_filtered_analytics_insights_and_csv_export_are_user_scoped(client: ApiClient) -> None:
    register(client, "analytics@example.com")
    register(client, "private@example.com")
    token = login(client, "analytics@example.com")
    private_token = login(client, "private@example.com")
    category = create_custom_category(client, token, "Analytics Food")
    private_category = create_custom_category(client, private_token, "Private Food")

    create_expense(client, token, category["id"], amount=100, description="January cash", date="2026-01-15", payment_method="cash")
    create_expense(client, token, category["id"], amount=50, description="February card", date="2026-02-15", payment_method="credit_card")
    create_expense(client, token, category["id"], amount=25, description="March cash", date="2026-03-15", payment_method="cash")
    create_expense(client, token, category["id"], amount=3, description="=1+1", date="2026-01-20", payment_method="other")
    create_expense(client, private_token, private_category["id"], amount=999, description="Private expense", date="2026-02-15")

    filtered = client.get(
        "/api/dashboard/summary?start_date=2026-01-01&end_date=2026-02-28&payment_method=cash",
        headers=auth(token),
    )
    assert filtered.status_code == 200
    summary = filtered.json()
    assert summary["total_spending"] == 100
    assert summary["expense_count"] == 1
    assert summary["monthly_spending"][0]["month"] == "2026-01"
    assert summary["monthly_spending"][-1]["month"] == "2026-02"
    assert summary["insights"]["highest_spending_category"] == "Analytics Food"
    assert summary["insights"]["highest_spending_month"] == "Jan 2026"
    assert summary["highest_expenses"][0]["description"] == "January cash"
    assert summary["payment_method_spending"] == [{"payment_method": "cash", "total": 100, "expense_count": 1}]

    category_filtered = client.get(
        f"/api/dashboard/summary?category_id={category['id']}",
        headers=auth(token),
    )
    assert category_filtered.status_code == 200
    assert category_filtered.json()["total_spending"] == 178
    assert {item["payment_method"]: item["total"] for item in category_filtered.json()["payment_method_spending"]} == {
        "cash": 125,
        "credit_card": 50,
        "other": 3,
    }

    invalid_range = client.get(
        "/api/dashboard/summary?start_date=2026-03-01&end_date=2026-02-01",
        headers=auth(token),
    )
    assert invalid_range.status_code == 422

    invalid_payment = client.get(
        "/api/dashboard/summary?payment_method=crypto",
        headers=auth(token),
    )
    assert invalid_payment.status_code == 422

    export = client.get(
        "/api/dashboard/export.csv?start_date=2026-01-01&end_date=2026-02-28",
        headers=auth(token),
    )
    assert export.status_code == 200
    assert export.headers["content-type"].startswith("text/csv")
    assert "January cash" in export.text
    assert "'=1+1" in export.text
    assert "February card" in export.text
    assert "March cash" not in export.text
    assert "Private expense" not in export.text

    unauthenticated_export = client.get("/api/dashboard/export.csv")
    assert unauthenticated_export.status_code == 401
    assert client.get("/api/budgets").status_code == 401
    assert client.get("/api/analysis/spending").status_code == 401
    assert client.post("/api/assistant/chat", json={"message": "summary"}).status_code == 401

    private_summary = client.get("/api/dashboard/summary", headers=auth(private_token))
    assert private_summary.status_code == 200
    assert private_summary.json()["total_spending"] == 999
    assert "January cash" not in private_summary.text
    assert private_summary.json()["payment_method_spending"] == [{"payment_method": "cash", "total": 999, "expense_count": 1}]

    private_export = client.get("/api/dashboard/export.csv", headers=auth(private_token))
    assert private_export.status_code == 200
    assert "Private expense" in private_export.text
    assert "January cash" not in private_export.text


def test_analytics_page_alias_and_profile_currency_contract(client: ApiClient) -> None:
    register(client, "currency@example.com")
    token = login(client, "currency@example.com")

    updated_profile = client.put(
        "/api/users/me",
        headers=auth(token),
        json={"currency": "EUR"},
    )
    assert updated_profile.status_code == 200
    assert updated_profile.json()["currency"] == "EUR"

    analytics_page = client.get("/analytics")
    assert analytics_page.status_code == 200
    assert "Dashboard" in analytics_page.text

    summary = client.get("/api/dashboard/summary", headers=auth(token))
    assert summary.status_code == 200
    assert summary.json()["currency"] == "EUR"


def test_production_configuration_requires_strong_secret() -> None:
    with pytest.raises(ValidationError):
        Settings(environment="production", jwt_secret_key="too-short")

    settings = Settings(
        environment="production",
        jwt_secret_key="a" * 32,
        cors_allowed_origins="https://app.example.com, https://admin.example.com",
    )
    assert settings.is_production is True
    assert settings.allowed_origins == ["https://app.example.com", "https://admin.example.com"]
    assert settings.server_host == "127.0.0.1"
    assert settings.server_port == 8000
    assert settings.trusted_proxy_ips == "127.0.0.1"
    with pytest.raises(ValidationError):
        Settings(
            environment="production",
            jwt_secret_key="a" * 32,
            cors_allowed_origins="*",
        )


def test_ai_rate_limiter_returns_retry_after_without_cross_user_blocking() -> None:
    limiter = AIRequestLimiter(max_requests=2, window_seconds=60)
    limiter.check(user_id=111, now=100)
    limiter.check(user_id=111, now=101)
    limiter.check(user_id=222, now=101)

    with pytest.raises(HTTPException) as error:
        limiter.check(user_id=111, now=102)
    assert error.value.status_code == 429
    assert error.value.headers["Retry-After"] == "58"
    limiter.check(user_id=111, now=161)


def test_spending_analysis_route_enforces_per_user_rate_limit(client: ApiClient, monkeypatch: pytest.MonkeyPatch) -> None:
    register(client, "analysis-rate-limit@example.com")
    token = login(client, "analysis-rate-limit@example.com")
    monkeypatch.setattr(analysis_routes, "ai_request_limiter", AIRequestLimiter(max_requests=1, window_seconds=60))

    first = client.get("/api/analysis/spending", headers=auth(token))
    second = client.get("/api/analysis/spending", headers=auth(token))

    assert first.status_code == 200
    assert second.status_code == 429
    assert second.headers["retry-after"]


def test_assistant_is_authenticated_scoped_and_uses_local_financial_context(client: ApiClient) -> None:
    register(client, "assistant-alice@example.com", "Alice")
    register(client, "assistant-bob@example.com", "Bob")
    alice_token = login(client, "assistant-alice@example.com")
    bob_token = login(client, "assistant-bob@example.com")
    alice_category = create_custom_category(client, alice_token, "Alice Food")
    bob_category = create_custom_category(client, bob_token, "Bob Private")
    create_expense(client, alice_token, alice_category["id"], amount=42, description="Alice lunch")
    create_expense(client, bob_token, bob_category["id"], amount=999, description="Bob private purchase")

    response = client.post(
        "/api/assistant/chat",
        headers=auth(alice_token),
        json={"message": "Summarize my spending"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "calculated"
    assert body["currency"] == "USD"
    assert body["metrics"]["total_spending"] == 42
    assert "Alice lunch" in body["answer"]
    assert "Bob private purchase" not in body["answer"]

    assert client.post("/api/assistant/chat", json={"message": "Summarize my spending"}).status_code == 401


def test_assistant_validates_messages_and_serves_page_assets(client: ApiClient) -> None:
    register(client, "assistant-validation@example.com")
    token = login(client, "assistant-validation@example.com")

    empty = client.post("/api/assistant/chat", headers=auth(token), json={"message": "   "})
    too_long = client.post("/api/assistant/chat", headers=auth(token), json={"message": "x" * 1001})
    page = client.get("/assistant", headers=auth(token))
    private_page = client.get("/assistant")
    script = client.get("/static/js/assistant.js")

    assert empty.status_code == 422
    assert too_long.status_code == 422
    assert page.status_code == 200
    assert private_page.status_code == 200
    assert "Financial assistant" in page.text
    assert script.status_code == 200
    assert "/api/assistant/chat" in script.text


def test_assistant_provider_errors_are_safe(client: ApiClient, monkeypatch: pytest.MonkeyPatch) -> None:
    register(client, "assistant-errors@example.com")
    token = login(client, "assistant-errors@example.com")

    def missing_provider() -> providers.FinancialAssistantProvider:
        raise providers.ProviderConfigurationError("secret detail should not escape")

    monkeypatch.setattr(providers, "get_provider", missing_provider)
    missing = client.post("/api/assistant/chat", headers=auth(token), json={"message": "How much did I spend?"})
    assert missing.status_code == 503
    assert missing.json()["detail"] == "The financial assistant is not configured yet."
    assert "secret detail" not in missing.text

    def failed_provider() -> providers.FinancialAssistantProvider:
        raise providers.ProviderRequestError("provider internals should not escape")

    monkeypatch.setattr(providers, "get_provider", failed_provider)
    failed = client.post("/api/assistant/chat", headers=auth(token), json={"message": "How much did I spend?"})
    assert failed.status_code == 502
    assert failed.json()["detail"] == "The financial assistant is temporarily unavailable."
    assert "provider internals" not in failed.text


def test_assistant_provider_can_be_mocked(client: ApiClient, monkeypatch: pytest.MonkeyPatch) -> None:
    register(client, "assistant-mock@example.com")
    token = login(client, "assistant-mock@example.com")

    class MockProvider:
        source = "mock"

        def answer(self, question: str, context: dict[str, object]) -> str:
            assert question == "Give me a summary"
            assert context["expense_count"] == 0
            return "Mocked assistant response"

    monkeypatch.setattr(providers, "get_provider", lambda: MockProvider())
    response = client.post(
        "/api/assistant/chat",
        headers=auth(token),
        json={"message": "Give me a summary"},
    )

    assert response.status_code == 200
    assert response.json()["answer"] == "Mocked assistant response"
    assert response.json()["source"] == "mock"


def test_budget_crud_monthly_progress_and_user_isolation(client: ApiClient) -> None:
    register(client, "budget-alice@example.com", "Alice")
    register(client, "budget-bob@example.com", "Bob")
    alice_token = login(client, "budget-alice@example.com")
    bob_token = login(client, "budget-bob@example.com")
    alice_category = create_custom_category(client, alice_token, "Alice groceries")
    bob_category = create_custom_category(client, bob_token, "Bob private")

    today = date.today()
    month_start = today.replace(day=1)
    previous_month = month_start - timedelta(days=1)
    create_expense(client, alice_token, alice_category["id"], amount=60, description="Current month", date=today.isoformat())
    create_expense(client, alice_token, alice_category["id"], amount=30, description="Previous month", date=previous_month.isoformat())
    create_expense(client, bob_token, bob_category["id"], amount=900, description="Other user's expense", date=today.isoformat())

    created = client.post(
        "/api/budgets",
        headers=auth(alice_token),
        json={"name": "Groceries", "amount": 100, "period": "monthly", "category_id": alice_category["id"]},
    )
    assert created.status_code == 201, created.text
    budget = created.json()
    assert budget["spent"] == 60
    assert budget["remaining"] == 40
    assert budget["percent_used"] == 60
    assert budget["status"] == "under"
    assert budget["category_name"] == "Alice groceries"
    assert budget["period_start"] == month_start.isoformat()

    listed = client.get("/api/budgets", headers=auth(alice_token))
    assert listed.status_code == 200
    assert len(listed.json()) == 1
    assert client.get("/api/budgets", headers=auth(bob_token)).json() == []
    assert client.get(f"/api/budgets/{budget['id']}", headers=auth(bob_token)).status_code == 404
    assert client.put(
        f"/api/budgets/{budget['id']}",
        headers=auth(bob_token),
        json={"name": "Stolen", "amount": 1, "period": "monthly", "category_id": bob_category["id"]},
    ).status_code == 404
    assert client.delete(f"/api/budgets/{budget['id']}", headers=auth(bob_token)).status_code == 404

    overall = client.post(
        "/api/budgets",
        headers=auth(alice_token),
        json={"name": "Everything", "amount": 75},
    )
    assert overall.status_code == 201
    assert overall.json()["category_name"] == "Overall"
    assert overall.json()["spent"] == 60
    assert overall.json()["status"] == "near"

    updated = client.put(
        f"/api/budgets/{budget['id']}",
        headers=auth(alice_token),
        json={"name": "Groceries updated", "amount": 75, "period": "monthly", "category_id": alice_category["id"]},
    )
    assert updated.status_code == 200
    assert updated.json()["status"] == "near"

    updated = client.put(
        f"/api/budgets/{budget['id']}",
        headers=auth(alice_token),
        json={"name": "Groceries updated", "amount": 50, "period": "monthly", "category_id": alice_category["id"]},
    )
    assert updated.status_code == 200
    assert updated.json()["status"] == "over"
    assert updated.json()["remaining"] == -10

    assert client.delete(f"/api/budgets/{budget['id']}", headers=auth(alice_token)).status_code == 204
    assert client.delete(f"/api/budgets/{overall.json()['id']}", headers=auth(alice_token)).status_code == 204
    assert client.get(f"/api/budgets/{budget['id']}", headers=auth(alice_token)).status_code == 404


def test_budget_validation_auth_and_category_delete_interaction(client: ApiClient) -> None:
    register(client, "budget-validation@example.com")
    register(client, "budget-owner@example.com")
    token = login(client, "budget-validation@example.com")
    other_token = login(client, "budget-owner@example.com")
    category = create_custom_category(client, token, "Budget category")
    other_category = create_custom_category(client, other_token, "Other category")

    assert client.get("/api/budgets").status_code == 401
    assert client.post("/api/budgets", json={"name": "Unauth", "amount": 10}).status_code == 401

    zero_amount = client.post("/api/budgets", headers=auth(token), json={"name": "Bad", "amount": 0})
    negative_amount = client.post("/api/budgets", headers=auth(token), json={"name": "Bad", "amount": -2})
    subcent_amount = client.post("/api/budgets", headers=auth(token), json={"name": "Bad", "amount": 0.001})
    invalid_period = client.post("/api/budgets", headers=auth(token), json={"name": "Bad", "amount": 10, "period": "weekly"})
    foreign_category = client.post(
        "/api/budgets",
        headers=auth(token),
        json={"name": "Bad category", "amount": 10, "category_id": other_category["id"]},
    )
    assert zero_amount.status_code == 422
    assert negative_amount.status_code == 422
    assert subcent_amount.status_code == 422
    assert invalid_period.status_code == 422
    assert foreign_category.status_code == 404

    budget = client.post(
        "/api/budgets",
        headers=auth(token),
        json={"name": "Protect category", "amount": 100, "category_id": category["id"]},
    ).json()
    blocked_delete = client.delete(f"/api/categories/{category['id']}", headers=auth(token))
    assert blocked_delete.status_code == 409
    assert "Delete budgets" in blocked_delete.json()["detail"]

    assert client.delete(f"/api/budgets/{budget['id']}", headers=auth(token)).status_code == 204
    assert client.delete(f"/api/categories/{category['id']}", headers=auth(token)).status_code == 204


def test_spending_analysis_is_authenticated_aggregated_and_user_scoped(client: ApiClient, monkeypatch: pytest.MonkeyPatch) -> None:
    register(client, "analysis-alice@example.com", "Alice")
    register(client, "analysis-bob@example.com", "Bob")
    alice_token = login(client, "analysis-alice@example.com")
    bob_token = login(client, "analysis-bob@example.com")
    alice_category = create_custom_category(client, alice_token, "Alice groceries")
    bob_category = create_custom_category(client, bob_token, "Bob private")

    today = date.today()
    first_of_month = today.replace(day=1)
    previous_month_end = first_of_month - timedelta(days=1)
    previous_months = [previous_month_end]
    for _ in range(2):
        previous_months.append(previous_months[-1].replace(day=1) - timedelta(days=1))
    for expense_date in previous_months:
        create_expense(client, alice_token, alice_category["id"], amount=10, description="Repeated grocery purchase", date=expense_date.isoformat())
    create_expense(client, alice_token, alice_category["id"], amount=100, description="Alice transaction detail", date=today.isoformat())
    create_expense(client, bob_token, bob_category["id"], amount=900, description="Bob private transaction", date=today.isoformat())

    provider_context: dict[str, object] = {}

    class MockAnalysisProvider:
        source = "mock"

        def analyze(self, statistics: dict[str, object]) -> str:
            provider_context.update(statistics)
            assert "Alice transaction detail" not in str(statistics)
            assert "Bob private transaction" not in str(statistics)
            assert "analysis-alice@example.com" not in str(statistics)
            return "Grounded mocked analysis"

    monkeypatch.setattr(providers, "get_provider", lambda: MockAnalysisProvider())
    response = client.get("/api/analysis/spending", headers=auth(alice_token))
    assert response.status_code == 200
    result = response.json()
    assert result["analysis"] == "Grounded mocked analysis"
    assert result["source"] == "mock"
    assert result["stats"]["expense_count"] == 4
    assert result["stats"]["total_spending"] == 130
    assert result["stats"]["category_totals"][0]["share_percent"] == 100
    assert result["stats"]["current_month_spike"] is not None
    assert result["stats"]["recurring_patterns"][0]["occurrences"] == 3
    assert "description" not in result["stats"]
    assert "Bob private transaction" not in response.text
    assert provider_context["total_spending"] == 130
    assert client.get("/api/analysis/spending", headers=auth(bob_token)).json()["stats"]["total_spending"] == 900
    assert client.get("/api/analysis/spending").status_code == 401


def test_spending_analysis_insufficient_data_and_provider_errors(client: ApiClient, monkeypatch: pytest.MonkeyPatch) -> None:
    register(client, "analysis-empty@example.com")
    token = login(client, "analysis-empty@example.com")

    def provider_should_not_run() -> providers.FinancialAssistantProvider:
        raise AssertionError("provider should not run when there is insufficient data")

    monkeypatch.setattr(providers, "get_provider", provider_should_not_run)
    empty = client.get("/api/analysis/spending", headers=auth(token))
    assert empty.status_code == 200
    assert empty.json()["insufficient_data"] is True
    assert "at least three expenses" in empty.json()["analysis"]

    category = create_custom_category(client, token, "Analysis")
    for description, amount in [("Entry one", 5), ("Entry two", 7), ("Entry three", 9)]:
        create_expense(client, token, category["id"], amount=amount, description=description, date=date.today().isoformat())

    def missing_provider() -> providers.FinancialAssistantProvider:
        raise providers.ProviderConfigurationError("private config detail")

    monkeypatch.setattr(providers, "get_provider", missing_provider)
    unconfigured = client.get("/api/analysis/spending", headers=auth(token))
    assert unconfigured.status_code == 503
    assert "private config detail" not in unconfigured.text

    def failed_provider() -> providers.FinancialAssistantProvider:
        raise providers.ProviderRequestError("provider internals")

    monkeypatch.setattr(providers, "get_provider", failed_provider)
    failed = client.get("/api/analysis/spending", headers=auth(token))
    assert failed.status_code == 502
    assert failed.json()["detail"] == "Spending analysis is temporarily unavailable."
    assert "provider internals" not in failed.text
