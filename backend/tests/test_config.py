import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.config import Settings
from app.main import app


def test_settings_read_from_environment(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@db:5432/other")

    assert Settings(_env_file=None).database_url == "postgresql+psycopg://u:p@db:5432/other"


def test_settings_have_local_default(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)

    assert Settings(_env_file=None).database_url.startswith("postgresql+psycopg://")


def test_short_jwt_secret_is_rejected(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "too-short")

    with pytest.raises(ValidationError, match="at least 32 characters"):
        Settings(_env_file=None)


def test_blank_jwt_secret_means_unset(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "")

    assert Settings(_env_file=None).jwt_secret is None


def test_api_refuses_to_start_without_jwt_secret(monkeypatch):
    monkeypatch.setattr("app.main.get_settings", lambda: Settings(_env_file=None, jwt_secret=None))

    with pytest.raises(RuntimeError, match="JWT_SECRET"), TestClient(app):
        pass
