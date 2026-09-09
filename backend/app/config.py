"""Configuration management for the application."""

import os
from functools import lru_cache
from pydantic import ConfigDict
from pydantic_settings import BaseSettings


VALID_APP_ENVS = frozenset({"development", "staging", "production"})
VALID_AUTOMATION_MODES = frozenset({"mock", "live"})


def app_environment() -> str:
    """Return the explicit application environment with legacy compatibility."""
    return os.getenv("APP_ENV", os.getenv("ENVIRONMENT", "development")).lower()


def automation_mode() -> str:
    """Return the selected automation mode, defaulting safely to mock."""
    return os.getenv("AUTOMATION_MODE", "mock").lower()


def validate_automation_configuration() -> None:
    """Reject unsafe or ambiguous mock/live combinations at process startup."""
    environment = app_environment()
    mode = automation_mode()
    if environment not in VALID_APP_ENVS:
        raise ValueError("APP_ENV must be development, staging, or production")
    if mode not in VALID_AUTOMATION_MODES:
        raise ValueError("AUTOMATION_MODE must be mock or live")
    if environment in {"staging", "production"} and mode != "live":
        raise ValueError("AUTOMATION_MODE=live is required outside development")


class Settings(BaseSettings):
    """Application settings from environment variables."""
    
    # Database
    database_url: str = os.getenv(
        "DATABASE_URL", 
        "sqlite:///./data/signup_automation.db"
    )
    redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    
    # API
    api_title: str = "Signup Automation API"
    api_version: str = "1.0.0"
    
    # Frontend
    frontend_origin: str = os.getenv(
        "FRONTEND_ORIGIN", 
        "http://127.0.0.1:5173"
    )
    additional_cors_origins: str = os.getenv(
        "ADDITIONAL_CORS_ORIGINS",
        ""
    )
    
    # Worker
    worker_id: str = os.getenv("WORKER_ID", "")
    max_workers: int = int(os.getenv("MAX_WORKERS", "1"))
    worker_lease_seconds: float = float(os.getenv("WORKER_LEASE_SECONDS", "30"))
    
    # Batch processing
    target_batch_size: int = int(os.getenv("TARGET_BATCH_SIZE", "1000"))
    max_signup_retries: int = int(os.getenv("MAX_SIGNUP_RETRIES", "3"))
    retry_delay_seconds: float = float(os.getenv("RETRY_DELAY_SECONDS", "2"))
    retry_backoff_multiplier: float = float(os.getenv("RETRY_BACKOFF_MULTIPLIER", "2"))
    
    # Google Sheets
    google_sheets_id: str = os.getenv("GOOGLE_SHEETS_ID", "")
    google_sheets_worksheet: str = os.getenv("GOOGLE_SHEETS_WORKSHEET", "Results")
    google_service_account_json: str = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "")
    
    # Logging
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    app_env: str = os.getenv("APP_ENV", "development")
    environment: str = app_environment()
    automation_mode: str = automation_mode()
    jwt_secret: str = os.getenv("JWT_SECRET", "development-only-change-me")
    jwt_algorithm: str = os.getenv("JWT_ALGORITHM", "HS256")
    auth_required: bool = os.getenv("AUTH_REQUIRED", "false").lower() == "true"
    api_rate_limit_per_minute: int = int(os.getenv("API_RATE_LIMIT_PER_MINUTE", "100"))
    authorized_test_base_url: str = os.getenv("AUTHORIZED_TEST_BASE_URL", "")
    
    model_config = ConfigDict(env_file=".env", case_sensitive=False, extra="ignore")

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"
@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
