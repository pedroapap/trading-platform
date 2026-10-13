from app.security import decode_access_token
from tests.helpers import USER_EMAIL, USER_PASSWORD


def login(client, username: str, password: str):
    return client.post("/api/auth/login", data={"username": username, "password": password})


def test_correct_credentials_return_a_token_for_the_user(client, user):
    response = login(client, USER_EMAIL, USER_PASSWORD)

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert decode_access_token(body["access_token"]) == str(user.id)


def test_email_is_case_insensitive(client, user):
    assert login(client, USER_EMAIL.upper(), USER_PASSWORD).status_code == 200


def test_wrong_password_is_rejected(client, user):
    response = login(client, USER_EMAIL, "not-the-password")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_unknown_email_is_rejected_the_same_way(client, user):
    response = login(client, "nobody@example.com", USER_PASSWORD)

    assert response.status_code == 401
    assert response.json() == {"detail": "Incorrect email or password"}


def test_disabled_account_cannot_log_in(client, db_session, user):
    user.is_active = False
    db_session.commit()

    assert login(client, USER_EMAIL, USER_PASSWORD).status_code == 403
