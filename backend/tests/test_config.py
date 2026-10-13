from app.config import Settings


def test_settings_read_from_environment(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@db:5432/other")

    assert Settings(_env_file=None).database_url == "postgresql+psycopg://u:p@db:5432/other"


def test_settings_have_local_default(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)

    assert Settings(_env_file=None).database_url.startswith("postgresql+psycopg://")
