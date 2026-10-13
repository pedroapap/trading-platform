from sqlalchemy import select

from app.models import User
from app.security import verify_password

ACCOUNT = {"email": "Trader@Example.com", "password": "a-long-enough-password"}


def test_first_registration_creates_the_account(client, db_session):
    response = client.post("/api/auth/register", json=ACCOUNT)

    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "trader@example.com"
    assert body["is_active"] is True
    assert "password_hash" not in body

    user = db_session.scalars(select(User)).one()
    assert verify_password(ACCOUNT["password"], user.password_hash)


def test_registration_closes_once_an_account_exists(client):
    client.post("/api/auth/register", json=ACCOUNT)

    response = client.post(
        "/api/auth/register", json={"email": "other@example.com", "password": "x" * 12}
    )

    assert response.status_code == 403


def test_registration_validates_email_and_password(client):
    bad_email = client.post("/api/auth/register", json={**ACCOUNT, "email": "not-an-email"})
    short_password = client.post("/api/auth/register", json={**ACCOUNT, "password": "short"})

    assert bad_email.status_code == 422
    assert short_password.status_code == 422
