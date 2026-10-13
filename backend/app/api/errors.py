"""Map domain errors raised by services to HTTP responses."""

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.errors import ConflictError, DomainError, InvalidOperationError, NotFoundError

_STATUS_CODES: dict[type[DomainError], int] = {
    NotFoundError: status.HTTP_404_NOT_FOUND,
    ConflictError: status.HTTP_409_CONFLICT,
    InvalidOperationError: status.HTTP_422_UNPROCESSABLE_CONTENT,
}


async def _domain_error(_: Request, exc: Exception) -> JSONResponse:
    code = next(
        (code for error, code in _STATUS_CODES.items() if isinstance(exc, error)),
        status.HTTP_400_BAD_REQUEST,
    )
    return JSONResponse({"detail": str(exc)}, status_code=code)


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(DomainError, _domain_error)
