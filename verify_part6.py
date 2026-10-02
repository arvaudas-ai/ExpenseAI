import json
import urllib.request
import urllib.error

base = "http://127.0.0.1:8003"


def request(path, method="GET", payload=None, token=None):
    data = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request(base + path, data=data, method=method, headers={"Content-Type": "application/json"})
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = resp.read().decode()
            return resp.status, json.loads(body) if body else None
    except urllib.error.HTTPError as exc:
        body = exc.read().decode()
        try:
            parsed = json.loads(body)
        except Exception:
            parsed = body
        return exc.code, parsed

alice = {"name": "Alice User", "email": "alice@example.com", "password": "Password123", "password_confirmation": "Password123"}
status, body = request("/api/auth/register", "POST", alice)
print("ALICE_REGISTER", status, body)
assert status == 201, (status, body)

status, body = request("/api/auth/login", "POST", {"email": alice["email"], "password": alice["password"]})
print("ALICE_LOGIN", status, body)
assert status == 200, (status, body)
alice_token = body["access_token"]

bob = {"name": "Bob User", "email": "bob@example.com", "password": "Password123", "password_confirmation": "Password123"}
status, body = request("/api/auth/register", "POST", bob)
print("BOB_REGISTER", status, body)
assert status == 201, (status, body)

status, body = request("/api/auth/login", "POST", {"email": bob["email"], "password": bob["password"]})
print("BOB_LOGIN", status, body)
assert status == 200, (status, body)
bob_token = body["access_token"]

payload = {"amount": 125.5, "category": "Food", "description": "Lunch", "date": "2025-01-15", "payment_method": "credit_card"}
status, body = request("/api/expenses", "POST", payload, alice_token)
print("ALICE_CREATE_EXPENSE", status, body)
assert status == 201, (status, body)
alice_expense_id = body["id"]

status, body = request("/api/expenses", "GET", None, alice_token)
print("ALICE_LIST", status, body)
assert status == 200 and len(body) == 1 and body[0]["id"] == alice_expense_id, (status, body)

status, body = request(f"/api/expenses/{alice_expense_id}", "GET", None, bob_token)
print("BOB_GET_ALICE_EXPENSE", status, body)
assert status == 404, (status, body)

bob_expense = {"amount": 89.99, "category": "Transport", "description": "Fuel", "date": "2025-01-16", "payment_method": "cash"}
status, body = request("/api/expenses", "POST", bob_expense, bob_token)
print("BOB_CREATE_EXPENSE", status, body)
assert status == 201, (status, body)
bob_expense_id = body["id"]

status, body = request("/api/expenses", "GET", None, alice_token)
print("ALICE_LIST_AFTER_BOB", status, body)
assert status == 200 and len(body) == 1 and body[0]["id"] == alice_expense_id, (status, body)

status, body = request(f"/api/expenses/{alice_expense_id}", "PUT", {"amount": 200.0, "description": "Team lunch updated"}, alice_token)
print("ALICE_UPDATE_EXPENSE", status, body)
assert status == 200 and body["amount"] == 200.0 and body["description"] == "Team lunch updated", (status, body)

status, body = request(f"/api/expenses/{alice_expense_id}", "PUT", {"amount": 999.99}, bob_token)
print("BOB_UPDATE_ALICE_EXPENSE", status, body)
assert status == 404, (status, body)

status, body = request(f"/api/expenses/{bob_expense_id}", "DELETE", None, bob_token)
print("BOB_DELETE_EXPENSE", status, body)
assert status == 204, (status, body)

status, body = request("/api/expenses", "GET", None, bob_token)
print("BOB_LIST_AFTER_DELETE", status, body)
assert status == 200 and body == [], (status, body)

print("ALL_PART6_EXPENSE_CHECKS_PASSED")
