"""Entry point for the TraceMind TM server HTTP API."""

from fastapi import FastAPI

from tm.server.config import ServerConfig
from tm.server.routes_controller import create_controller_router


def create_app(config: ServerConfig | None = None) -> FastAPI:
    cfg = config or ServerConfig()
    app = FastAPI(title="TraceMind Controller Server API")
    app.include_router(create_controller_router(cfg))
    return app


def _create_default_app() -> FastAPI:
    return create_app()


app = _create_default_app()
