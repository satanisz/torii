"""FastAPI factory: foundation only; protected product routes land with OIDC tests."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse

from torii_api.config import Settings
from torii_api.domain.errors import DomainError
from torii_api.http.middleware import EnvelopeMiddleware
from torii_api.http.problems import problem
from torii_api.storage.database import is_ready, make_engine


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = make_engine(config.database_url)
        app.state.engine = engine
        try:
            yield
        finally:
            await run_in_threadpool(engine.dispose)

    app = FastAPI(
        title="Torii control plane",
        version="0.1.0",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.settings = config
    app.add_middleware(EnvelopeMiddleware, allowed_host=urlsplit(config.public_url).netloc)

    @app.exception_handler(DomainError)
    async def domain_error(request: Request, exc: DomainError) -> JSONResponse:
        return problem(exc, request.state.request_id)

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException) -> JSONResponse:
        codes = {404: "not_found", 405: "method_not_allowed"}
        response = problem(
            DomainError(exc.status_code, codes.get(exc.status_code, "http_error")),
            request.state.request_id,
        )
        if exc.status_code == 405 and exc.headers and "Allow" in exc.headers:
            response.headers["Allow"] = exc.headers["Allow"]
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        # Do not echo pydantic input/context, or attacker-controlled extra field names.
        return problem(DomainError(422, "validation_failed"), request.state.request_id)

    @app.get("/health/live", include_in_schema=False)
    async def live(request: Request) -> dict[str, str]:
        if await request.body():
            raise DomainError(400, "unexpected_body")
        return {"status": "live"}

    @app.get("/health/ready", include_in_schema=False)
    async def ready(request: Request) -> dict[str, str]:
        if await request.body():
            raise DomainError(400, "unexpected_body")
        if not await run_in_threadpool(is_ready, request.app.state.engine):
            raise DomainError(503, "not_ready")
        return {"status": "ready"}

    return app
