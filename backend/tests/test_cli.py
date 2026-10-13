import io
from contextlib import contextmanager

import pytest
from sqlalchemy import func, select

from app import cli
from app.models import User


@pytest.fixture
def run_cli(db_session, monkeypatch):
    @contextmanager
    def test_session():
        yield db_session

    monkeypatch.setattr(cli, "session_scope", test_session)

    def run(email: str, password: str) -> int:
        monkeypatch.setattr("sys.stdin", io.StringIO(password + "\n"))
        return cli.main(["create-user", "--email", email, "--password-stdin"])

    return run


def test_cli_user_can_log_in(run_cli, client):
    assert run_cli("Cli@Example.com", "a-long-enough-password") == 0

    response = client.post(
        "/api/auth/login",
        data={"username": "cli@example.com", "password": "a-long-enough-password"},
    )
    assert response.status_code == 200


def test_cli_rejects_a_duplicate_email(run_cli, capsys):
    run_cli("cli@example.com", "a-long-enough-password")

    assert run_cli("cli@example.com", "another-long-password") == 1
    assert "already exists" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("email", "password"),
    [("not-an-email", "a-long-enough-password"), ("cli@example.com", "short")],
)
def test_cli_validates_input(run_cli, db_session, email, password):
    assert run_cli(email, password) == 1
    assert db_session.scalar(select(func.count()).select_from(User)) == 0
