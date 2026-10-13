"""Application settings, read from environment variables and the repo-root `.env`."""

from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=REPO_ROOT / ".env", extra="ignore")

    database_url: str = "postgresql+psycopg://trader:trader@localhost:5432/trading"
    # Optional here so migrations and CLI tools run without it; the API refuses to start unset.
    jwt_secret: SecretStr | None = None
    jwt_expire_minutes: int = 60 * 24 * 7

    @field_validator("jwt_secret", mode="before")
    @classmethod
    def _blank_secret_is_unset(cls, value: object) -> object:
        return value or None

    @field_validator("jwt_secret")
    @classmethod
    def _secret_is_long_enough(cls, value: SecretStr | None) -> SecretStr | None:
        if value is not None and len(value.get_secret_value()) < 32:
            raise ValueError("JWT_SECRET must be at least 32 characters")
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
