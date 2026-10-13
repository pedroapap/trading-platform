"""FastAPI application entry point."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.errors import register_error_handlers
from app.api.routes import auth, backtests, health, market_data, strategies, trades
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
app.include_router(auth.router, prefix="/api")
app.include_router(trades.router, prefix="/api")
app.include_router(market_data.router, prefix="/api")
app.include_router(strategies.router, prefix="/api")
app.include_router(backtests.router, prefix="/api")

register_error_handlers(app)
