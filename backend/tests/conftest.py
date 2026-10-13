"""Shared fixtures: a migrated throwaway database and per-test transactional sessions.

Tests run against `<app database>_test` (or TEST_DATABASE_URL), recreated and migrated
once per session. Each test runs inside a transaction that is rolled back afterwards;
the session joins it via savepoints, so code under test may call `commit()` freely.
"""

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import URL, Engine, create_engine, make_url, text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.main import app
from app.models import User
from app.services import users
from tests.helpers import USER_EMAIL, USER_PASSWORD

# Settings are read lazily, so this still applies to everything the tests touch.
os.environ.setdefault("JWT_SECRET", "test-only-jwt-secret-" + "0" * 32)

BACKEND_DIR = Path(__file__).resolve().parents[1]


def _test_database_url() -> URL:
    if url := os.environ.get("TEST_DATABASE_URL"):
        return make_url(url)
    app_url = make_url(get_settings().database_url)
    return app_url.set(database=f"{app_url.database}_test")


def _recreate_database(url: URL) -> None:
    admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{url.database}" WITH (FORCE)'))
        conn.execute(text(f'CREATE DATABASE "{url.database}"'))
    admin.dispose()


@pytest.fixture(scope="session")
def alembic_config() -> Config:
    config = Config(BACKEND_DIR / "alembic.ini", attributes={"configure_logger": False})
    rendered = _test_database_url().render_as_string(hide_password=False).replace("%", "%%")
    config.set_main_option("sqlalchemy.url", rendered)
    return config


@pytest.fixture(scope="session")
def engine(alembic_config: Config) -> Iterator[Engine]:
    url = _test_database_url()
    _recreate_database(url)
    command.upgrade(alembic_config, "head")
    engine = create_engine(url)
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(engine: Engine) -> Iterator[Session]:
    with engine.connect() as connection:
        transaction = connection.begin()
        session = Session(
            bind=connection,
            join_transaction_mode="create_savepoint",
            expire_on_commit=False,
        )
        try:
            yield session
        finally:
            session.close()
            transaction.rollback()


@pytest.fixture
def client(db_session: Session) -> Iterator[TestClient]:
    def override_get_db() -> Iterator[Session]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def user(db_session: Session) -> User:
    return users.create_user(db_session, USER_EMAIL, USER_PASSWORD)
