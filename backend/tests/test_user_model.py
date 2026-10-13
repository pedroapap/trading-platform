import pytest
from sqlalchemy.exc import IntegrityError

from app.models import User


def test_user_gets_server_defaults(db_session):
    user = User(email="me@example.com", password_hash="x")
    db_session.add(user)
    db_session.flush()
    db_session.refresh(user)

    assert user.id is not None
    assert user.is_active is True
    assert user.created_at.tzinfo is not None


def test_duplicate_email_is_rejected(db_session):
    db_session.add(User(email="me@example.com", password_hash="x"))
    db_session.flush()

    db_session.add(User(email="me@example.com", password_hash="y"))
    with pytest.raises(IntegrityError):
        db_session.flush()
