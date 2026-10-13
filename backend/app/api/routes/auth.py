from fastapi import APIRouter, HTTPException, status

from app.deps import DbSession
from app.models import User
from app.schemas.auth import RegisterRequest, UserRead
from app.services import users

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def register(body: RegisterRequest, db: DbSession) -> User:
    try:
        return users.register_first_user(db, body.email, body.password)
    except users.RegistrationClosedError:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Registration is closed: the account already exists"
        ) from None
