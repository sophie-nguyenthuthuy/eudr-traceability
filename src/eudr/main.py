"""FastAPI application factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from starlette.responses import Response

from eudr import __version__
from eudr.api.router import api_router
from eudr.config import get_settings
from eudr.errors import EUDRError
from eudr.logging_config import configure_logging, get_logger

log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:  # noqa: ARG001
    configure_logging()
    settings = get_settings()
    log.info("app.starting", env=settings.app_env, version=__version__)
    yield
    log.info("app.stopping")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="EUDR Traceability",
        description=(
            "Plot-level traceability and Due Diligence Statement service for "
            "Vietnamese coffee, rubber, and wood exports under EU Regulation 2023/1115."
        ),
        version=__version__,
        docs_url="/docs",
        redoc_url=None,
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    app.include_router(api_router)

    @app.exception_handler(EUDRError)
    async def _eudr_error_handler(request: Request, exc: EUDRError) -> JSONResponse:
        log.warning(
            "domain.error",
            path=request.url.path,
            code=exc.code,
            status=exc.status_code,
            message=exc.message,
        )
        body: dict[str, Any] = {
            "type": f"urn:eudr:error:{exc.code}",
            "title": exc.code.replace("_", " "),
            "status": exc.status_code,
            "detail": exc.message,
        }
        if exc.details:
            body["details"] = exc.details
        return JSONResponse(status_code=exc.status_code, content=body)

    if settings.prometheus_metrics_enabled:

        @app.get("/metrics", include_in_schema=False)
        async def metrics() -> Response:
            return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    return app


app = create_app()
