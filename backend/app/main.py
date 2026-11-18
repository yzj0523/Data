"""HTTP foundation. Health describes this service, not dependency connectivity."""

import logging
from typing import Literal

from fastapi import APIRouter, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.config import ConfigurationError, Settings, load_settings
from app.api import ApiError
from app.sessions import router as sessions_router
from app.sources import router as sources_router
from app.preferences import router as preferences_router
from app.models import router as models_router
from app.provider import router as provider_router
from app.queries import router as queries_router
from app.shortcuts import router as shortcuts_router
from app.feedback import router as feedback_router

logger = logging.getLogger(__name__)


class ErrorDetail(BaseModel):
    code: str
    message: str
    fields: list[str] | None = None


class ErrorResponse(BaseModel):
    error: ErrorDetail


class ModelHealth(BaseModel):
    status: Literal["not_configured", "not_checked"]


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    environment: str
    model: ModelHealth


def error_response(
    status_code: int,
    code: str,
    message: str,
    *,
    fields: list[str] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    body = ErrorResponse(error=ErrorDetail(code=code, message=message, fields=fields))
    return JSONResponse(
        status_code=status_code,
        content=body.model_dump(exclude_none=True),
        headers=headers,
    )


class SafeServerErrorMiddleware:
    """Handle HTTP failures before Starlette can re-raise their sensitive text."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        response_started = False
        response_complete = False

        async def track_response(message: Message) -> None:
            nonlocal response_started, response_complete
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)
            if message["type"] == "http.response.body" and not message.get("more_body", False):
                response_complete = True

        try:
            await self.app(scope, receive, track_response)
        except Exception:
            # Even exception chains and type names can contain sensitive text.
            logger.error("Unhandled server error.")
            if not response_started:
                response = error_response(500, "internal_error", "Internal server error.")
                await response(scope, receive, send)
            elif not response_complete:
                # Preserve a truncated-response failure without exposing its cause
                # to Uvicorn or sending a second set of response headers.
                raise RuntimeError("Response interrupted by an internal error.") from None
            # A background-task failure cannot change an already complete response.


def create_app(settings: Settings | None = None) -> FastAPI:
    configuration_error = None
    if settings is None:
        try:
            settings = load_settings()
        except ConfigurationError as exc:
            configuration_error = exc

    app = FastAPI(
        title="AI Query API",
        version="0.1.0",
        debug=False,
        docs_url="/api/docs",
        redoc_url=None,
        openapi_url="/api/openapi.json",
    )
    app.state.settings = settings

    @app.exception_handler(ApiError)
    async def handle_api_error(request: Request, exc: ApiError) -> JSONResponse:
        return error_response(exc.status, exc.code, exc.message)

    @app.exception_handler(HTTPException)
    async def handle_http_error(request: Request, exc: HTTPException) -> JSONResponse:
        code, message = {
            404: ("not_found", "Resource not found."),
            405: ("method_not_allowed", "Method not allowed."),
        }.get(exc.status_code, ("http_error", "Request could not be completed."))
        return error_response(exc.status_code, code, message, headers=exc.headers)

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return error_response(422, "validation_error", "Invalid request.")

    api = APIRouter(prefix="/api")

    @api.get(
        "/health",
        response_model=HealthResponse,
        responses={503: {"model": ErrorResponse}},
    )
    async def health() -> HealthResponse | JSONResponse:
        if configuration_error is not None:
            return error_response(
                503,
                "configuration_error",
                "Invalid server configuration.",
                fields=configuration_error.fields,
            )

        assert settings is not None
        model_configured = all(
            (
                settings.default_model_base_url,
                settings.default_model_name,
                settings.default_model_api_key,
            )
        )
        return HealthResponse(
            environment=settings.environment,
            model=ModelHealth(
                status="not_checked" if model_configured else "not_configured"
            ),
        )

    api.include_router(sessions_router)
    api.include_router(sources_router)
    api.include_router(preferences_router)
    api.include_router(models_router)
    api.include_router(provider_router)
    api.include_router(queries_router)
    api.include_router(shortcuts_router)
    api.include_router(feedback_router)
    app.include_router(api)
    app.add_middleware(SafeServerErrorMiddleware)
    return app
