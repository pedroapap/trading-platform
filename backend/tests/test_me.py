import uuid

from app.security import create_access_token


def test_valid_token_returns_the_current_user(client, user, auth_headers):
    response = client.get("/api/auth/me", headers=auth_headers)

    assert response.status_code == 200
    assert response.json()["id"] == str(user.id)
    assert response.json()["email"] == user.email


def test_missing_token_is_unauthorized(client):
    response = client.get("/api/auth/me")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_garbage_token_is_unauthorized(client):
    response = client.get("/api/auth/me", headers={"Authorization": "Bearer not-a-jwt"})

    assert response.status_code == 401


def test_token_for_a_missing_user_is_unauthorized(client):
    token = create_access_token(str(uuid.uuid4()))

    response = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401


def test_token_with_a_non_uuid_subject_is_unauthorized(client):
    token = create_access_token("not-a-uuid")

    response = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401


def test_token_for_a_disabled_user_is_unauthorized(client, db_session, user, auth_headers):
    user.is_active = False
    db_session.commit()

    assert client.get("/api/auth/me", headers=auth_headers).status_code == 401
