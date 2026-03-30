from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str | None = None

    @field_validator("database_url", mode="before")
    @classmethod
    def use_psycopg3_driver(cls, v: str | None) -> str | None:
        """Map postgresql:// → postgresql+psycopg:// so SQLAlchemy uses psycopg v3."""
        if not v:
            return v
        if v.startswith("postgresql://") and not v.startswith("postgresql+"):
            return v.replace("postgresql://", "postgresql+psycopg://", 1)
        return v
    eia_api_key: str = ""
    # EIA Annual Energy Outlook API path segment, e.g. ``2025`` → ``/v2/aeo/2025/``
    eia_aeo_release: str = "2025"
    anthropic_api_key: str = ""
    admin_key: str = ""
    cors_origins: str = "http://localhost:5173"


settings = Settings()
