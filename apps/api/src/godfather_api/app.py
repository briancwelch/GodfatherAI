"""Application factory: versioned foundation, health probes and request telemetry."""

import asyncio
import logging
import re
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager, suppress
from time import perf_counter
from uuid import uuid4

from fastapi import APIRouter, FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.exc import SQLAlchemyError
from starlette.concurrency import run_in_threadpool

from godfather_api.account_providers import router as account_providers_router
from godfather_api.administration import router as administration_router
from godfather_api.agents import router as agents_router
from godfather_api.appearance import router as appearance_router
from godfather_api.artifacts import LocalArtifactStore
from godfather_api.authentication import router as authentication_router
from godfather_api.command_center import router as command_center_router
from godfather_api.config import Settings
from godfather_api.database import Database
from godfather_api.enrollment import router as enrollment_router
from godfather_api.inference import router as inference_router
from godfather_api.jobs import router as jobs_router
from godfather_api.logging import configure_logging, correlation_id
from godfather_api.nodes import router as nodes_router
from godfather_api.nodes import sweep_health
from godfather_api.provider_connections import router as provider_connections_router
from godfather_api.scheduler import scheduler_tick

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
        app.state.settings = config
        app.state.artifacts = LocalArtifactStore(config.artifact_directory)
        stop = asyncio.Event()

        async def monitor() -> None:
            while not stop.is_set():
                try:
                    await run_in_threadpool(sweep_health, app.state.database, config)
                    if config.scheduler_enabled:
                        await run_in_threadpool(scheduler_tick, app.state.database, config)
                except SQLAlchemyError as error:
                    logger.warning(
                        "health_scan.unavailable", extra={"error_type": type(error).__name__}
                    )
                with suppress(TimeoutError):
                    await asyncio.wait_for(stop.wait(), timeout=config.health_scan_seconds)

        task = asyncio.create_task(monitor()) if config.health_monitor_enabled else None
        logger.info("application.started")
        try:
            yield
        finally:
            stop.set()
            if task is not None:
                await task
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
    app.include_router(provider_connections_router)
    app.include_router(appearance_router)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, error: RequestValidationError) -> JSONResponse:
        # Never echo arbitrary payload values (including accidental credentials).
        return JSONResponse(
            {"detail": "Invalid request; consult the versioned API schema"}, status_code=422
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
            response.headers["Cache-Control"] = "no-store"
            response.headers["X-Content-Type-Options"] = "nosniff"
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
    app.include_router(nodes_router)
    app.include_router(jobs_router)
    from godfather_api.result_actions import router as result_actions_router

    app.include_router(result_actions_router)
    app.include_router(agents_router)
    from godfather_api.workloads import router as workloads_router

    app.include_router(workloads_router)
    app.include_router(inference_router)
    app.include_router(command_center_router)
    app.include_router(authentication_router)
    from godfather_api.account_profile import router as account_profile_router
    from godfather_api.workspace_archive import router as workspace_archive_router

    app.include_router(workspace_archive_router)
    app.include_router(account_profile_router)
    app.include_router(administration_router)
    app.include_router(account_providers_router)
    app.include_router(enrollment_router)
    return app
