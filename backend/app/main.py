"""FastAPI application entry point."""

from fastapi import FastAPI

from app.api.routes import health

app = FastAPI(
    title="Trading Platform",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
)

app.include_router(health.router, prefix="/api")
