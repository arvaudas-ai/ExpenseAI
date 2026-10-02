import secrets
from functools import lru_cache

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "ExpenseAI"
    environment: str = "development"
    database_url: str = "sqlite:///./expenseai.db"
    jwt_secret_key: str | None = None
    access_token_expire_minutes: int = Field(default=60, gt=0, le=1440)
    cors_allowed_origins: str = ""
    server_host: str = "127.0.0.1"
    server_port: int = Field(default=8000, gt=0, le=65535)
    trusted_proxy_ips: str = "127.0.0.1"
    ai_provider: str = "local"
    ai_api_key: str | None = None
    ai_model: str = "gpt-4o-mini"
    ai_base_url: str = "https://api.openai.com/v1"
    ai_timeout_seconds: int = Field(default=20, gt=0, le=120)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @model_validator(mode="after")
    def validate_deployment_settings(self) -> "Settings":
        self.environment = self.environment.strip().lower()
        if self.environment == "production":
            if not self.jwt_secret_key or len(self.jwt_secret_key) < 32:
                raise ValueError("JWT_SECRET_KEY must be set to at least 32 characters in production.")
            if "*" in self.allowed_origins:
                raise ValueError("CORS_ALLOWED_ORIGINS must not contain a wildcard in production.")
        elif not self.jwt_secret_key:
            self.jwt_secret_key = secrets.token_urlsafe(32)
        return self

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def allowed_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_allowed_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
