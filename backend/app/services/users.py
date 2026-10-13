"""User accounts. The platform is single-user: self-registration only creates the first one."""

from functools import lru_cache

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import User
from app.security import hash_password, verify_password

# Arbitrary advisory-lock key that serializes first-user registration.
_REGISTRATION_LOCK = 7_316_421


class RegistrationClosedError(Exception):
    """A user already exists."""


class EmailTakenError(Exception):
    """Another user already has this email."""


def normalize_email(email: str) -> str:
    return email.strip().lower()


def create_user(db: Session, email: str, password: str) -> User:
    user = User(email=normalize_email(email), password_hash=hash_password(password))
    db.add(user)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise EmailTakenError(email) from exc
    return user


def register_first_user(db: Session, email: str, password: str) -> User:
    # The lock makes concurrent registrations queue, so only one can see an empty table.
    db.execute(select(func.pg_advisory_xact_lock(_REGISTRATION_LOCK)))
    if db.scalar(select(func.count()).select_from(User)):
        db.rollback()
        raise RegistrationClosedError
    return create_user(db, email, password)


@lru_cache
def _dummy_hash() -> str:
    return hash_password("timing-equalizer")


def authenticate(db: Session, email: str, password: str) -> User | None:
    user = db.scalar(select(User).where(User.email == normalize_email(email)))
    if user is None:
        # Spend the same hashing time as a real check so response time doesn't reveal emails.
        verify_password(password, _dummy_hash())
        return None
    return user if verify_password(password, user.password_hash) else None
