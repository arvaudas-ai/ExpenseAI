import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db
from app.main import app
import app.main as main

engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
Base.metadata.create_all(engine)
main.create_database_tables = lambda: None


def override_get_db():
    yield Session(engine)


app.dependency_overrides[get_db] = override_get_db
print("BEFORE", flush=True)
client = TestClient(app)
print("CLIENT", flush=True)
response = client.post(
    "/api/auth/register",
    json={
        "name": "Alice",
        "email": "alice@example.com",
        "password": "Password123",
        "password_confirmation": "Password123",
    },
)
print("AFTER", response.status_code, response.text, flush=True)
