from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import Response

from app.api.routes.auth import router as auth_router
from app.api.routes.analysis import router as analysis_router
from app.api.routes.assistant import router as assistant_router
from app.api.routes.budgets import router as budgets_router
from app.api.routes.categories import router as categories_router
from app.api.routes.dashboard import router as dashboard_router
from app.api.routes.expenses import router as expenses_router
from app.api.routes.health import router as health_router
from app.api.routes.users import router as users_router
from app.core.config import get_settings
from app.db.init_db import create_database_tables

settings = get_settings()
APP_ROOT = Path(__file__).resolve().parent
app = FastAPI(title="ExpenseAI", version="0.1.0")


@app.exception_handler(RequestValidationError)
async def safe_validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    safe_errors = [
        {
            "loc": error.get("loc", ()),
            "msg": error.get("msg", "Invalid value."),
            "type": error.get("type", "value_error"),
        }
        for error in exc.errors()
    ]
    return JSONResponse(status_code=422, content={"detail": safe_errors})

if settings.allowed_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )


@app.middleware("http")
async def add_security_headers(request: Request, call_next) -> Response:
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    if settings.is_production:
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return response


@app.on_event("startup")
async def startup_event() -> None:
    create_database_tables()


app.include_router(health_router)
app.include_router(auth_router)
app.include_router(analysis_router)
app.include_router(assistant_router)
app.include_router(budgets_router)
app.include_router(users_router)
app.include_router(categories_router)
app.include_router(dashboard_router)
app.include_router(expenses_router)

app.mount("/static", StaticFiles(directory=APP_ROOT / "static"), name="static")


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(APP_ROOT / "templates/index.html")


@app.get("/login")
async def login_page() -> FileResponse:
    return FileResponse(APP_ROOT / "templates/login.html")


@app.get("/register")
async def register_page() -> FileResponse:
    return FileResponse(APP_ROOT / "templates/register.html")


@app.get("/dashboard")
async def dashboard_page() -> FileResponse:
    return FileResponse(APP_ROOT / "templates/dashboard.html")


@app.get("/analytics")
async def analytics_page() -> FileResponse:
    return FileResponse(APP_ROOT / "templates/dashboard.html")


@app.get("/assistant")
async def assistant_page() -> FileResponse:
    return FileResponse(APP_ROOT / "templates/assistant.html")


@app.get("/expenses")
async def expenses_page() -> FileResponse:
    return FileResponse(APP_ROOT / "templates/expenses.html")


@app.get("/settings")
async def settings_page() -> FileResponse:
    return FileResponse(APP_ROOT / "templates/settings.html")


@app.get("/categories")
async def categories_page() -> FileResponse:
    return FileResponse(APP_ROOT / "templates/categories.html")
