"""Application error types and the FastAPI exception handlers that turn every
error path (explicit, validation, or unhandled) into the single consistent
response envelope the frontend can rely on::

    {"success": false, "error": {"code": "...", "message": "..."}}

Unhandled exceptions are logged with a full traceback server-side and never
leak a traceback to the client.
"""
from __future__ import annotations

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import get_logger

logger = get_logger(__name__)


class AppError(Exception):
    """Base class for all intentionally-raised application errors."""

    def __init__(self, code: str, message: str, status_code: int = status.HTTP_400_BAD_REQUEST):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class NotFoundError(AppError):
    def __init__(self, message: str = "Resource not found", code: str = "NOT_FOUND"):
        super().__init__(code, message, status.HTTP_404_NOT_FOUND)


class ForbiddenError(AppError):
    def __init__(self, message: str = "You do not have access to this resource", code: str = "FORBIDDEN"):
        super().__init__(code, message, status.HTTP_403_FORBIDDEN)


class UnauthorizedError(AppError):
    def __init__(self, message: str = "Authentication required", code: str = "UNAUTHORIZED"):
        super().__init__(code, message, status.HTTP_401_UNAUTHORIZED)


class ConflictError(AppError):
    def __init__(self, message: str, code: str = "CONFLICT"):
        super().__init__(code, message, status.HTTP_409_CONFLICT)


class RateLimitedError(AppError):
    def __init__(self, message: str = "Too many requests, please try again later", code: str = "RATE_LIMITED"):
        super().__init__(code, message, status.HTTP_429_TOO_MANY_REQUESTS)


class NotImplementedYetError(AppError):
    """Used by routes belonging to a phase that hasn't been built yet."""

    def __init__(self, feature: str):
        super().__init__(
            code="NOT_IMPLEMENTED",
            message=f"{feature} is not implemented yet — planned for a later development phase.",
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
        )


def _envelope(code: str, message: str) -> dict:
    return {"success": False, "error": {"code": code, "message": message}}


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content=_envelope(exc.code, exc.message))

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_exception(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = {
            401: "UNAUTHORIZED",
            403: "FORBIDDEN",
            404: "NOT_FOUND",
            405: "METHOD_NOT_ALLOWED",
            429: "RATE_LIMITED",
        }.get(exc.status_code, "HTTP_ERROR")
        message = exc.detail if isinstance(exc.detail, str) else "Request failed"
        return JSONResponse(status_code=exc.status_code, content=_envelope(code, message))

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        first = exc.errors()[0] if exc.errors() else None
        message = "Request validation failed"
        if first:
            location = ".".join(str(part) for part in first.get("loc", []) if part != "body")
            message = f"{location}: {first.get('msg')}" if location else first.get("msg", message)
        return JSONResponse(
            status_code=422,
            content=_envelope("VALIDATION_ERROR", message),
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=_envelope("INTERNAL_SERVER_ERROR", "An unexpected error occurred"),
        )
