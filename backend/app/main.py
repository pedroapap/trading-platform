"""FastAPI application entry point."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import health
from app.config import get_settings


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    if get_settings().jwt_secret is None:
        raise RuntimeError("JWT_SECRET is not set; run `make setup` or see .env.example")
    yield


app = FastAPI(
    title="Trading Platform",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

app.include_router(health.router, prefix="/api")
