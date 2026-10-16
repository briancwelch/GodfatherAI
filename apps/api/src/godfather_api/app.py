"""Application factory: versioned foundation, health probes and request telemetry."""

import logging
import re
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from time import perf_counter
from uuid import uuid4

from fastapi import APIRouter, FastAPI, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.exc import SQLAlchemyError

from godfather_api.config import Settings
from godfather_api.database import Database
from godfather_api.logging import configure_logging, correlation_id

logger = logging.getLogger("godfather.api")
CORRELATION_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


class Health(BaseModel):
    status: str


class ApiInfo(BaseModel):
    service: str = "the-godfather"
    api_version: str = "v1"


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings if settings is not None else Settings()
    configure_logging(config.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.database = Database(config)
        logger.info("application.started")
        try:
            yield
        finally:
            app.state.database.close()
            logger.info("application.stopped")

    app = FastAPI(
        title="The Godfather API",
        version="0.1.0",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url="/api/v1/openapi.json",
    )

    @app.middleware("http")
    async def request_context(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        supplied = request.headers.getlist("x-correlation-id")
        request_id = (
            supplied[0]
            if len(supplied) == 1 and CORRELATION_PATTERN.fullmatch(supplied[0])
            else uuid4().hex
        )
        token = correlation_id.set(request_id)
        started = perf_counter()
        try:
            try:
                response = await call_next(request)
            except Exception as error:
                logger.error("request.failed", extra={"error_type": type(error).__name__})
                response = JSONResponse({"detail": "Internal server error"}, status_code=500)
            response.headers["X-Correlation-ID"] = request_id
            route = request.scope.get("route")
            logger.info(
                "request.completed",
                extra={
                    "method": request.method,
                    "route": getattr(route, "path", "unmatched"),
                    "status_code": response.status_code,
                    "duration_ms": round((perf_counter() - started) * 1000, 2),
                },
            )
            return response
        finally:
            correlation_id.reset(token)

    router = APIRouter(prefix="/api/v1")

    @router.get("", response_model=ApiInfo)
    def api_info() -> ApiInfo:
        return ApiInfo()

    @app.get("/health/live", response_model=Health)
    def live() -> Health:
        return Health(status="alive")

    @app.get("/health/ready", response_model=Health, responses={503: {"model": Health}})
    def ready(request: Request, response: Response) -> Health:
        database: Database = request.app.state.database
        try:
            if database.ready():
                return Health(status="ready")
        except SQLAlchemyError as error:
            logger.warning("database.unavailable", extra={"error_type": type(error).__name__})
        response.status_code = 503
        return Health(status="not_ready")

    app.include_router(router)
    return app
