"""
app/core/exceptions.py
──────────────────────
Centralized exception hierarchy + FastAPI exception handlers.

Pattern:
  - All domain errors extend AppException
  - Each error has a code (machine-readable) and message (human-readable)
  - FastAPI handlers catch them and return structured JSON
  - Unhandled errors are caught by the 500 handler and logged

Client always gets:
  {
    "error": {
      "code": "DOCUMENT_NOT_FOUND",
      "message": "Document with id=abc was not found",
      "request_id": "uuid"
    }
  }
"""

from __future__ import annotations

import traceback
import uuid
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.core.logging import get_logger

logger = get_logger(__name__)


# ─── Base ─────────────────────────────────────────────────────────────────────

class AppException(Exception):
    """Base for all domain exceptions."""

    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    code: str = "INTERNAL_ERROR"

    def __init__(self, message: str, detail: Any = None) -> None:
        self.message = message
        self.detail = detail
        super().__init__(message)


# ─── 400 Bad Request ──────────────────────────────────────────────────────────

class ValidationException(AppException):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    code = "VALIDATION_ERROR"


class UnsupportedFileTypeException(AppException):
    status_code = status.HTTP_400_BAD_REQUEST
    code = "UNSUPPORTED_FILE_TYPE"


class FileTooLargeException(AppException):
    status_code = status.HTTP_400_BAD_REQUEST
    code = "FILE_TOO_LARGE"


# ─── 401 / 403 ────────────────────────────────────────────────────────────────

class UnauthorizedException(AppException):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "UNAUTHORIZED"


class ForbiddenException(AppException):
    status_code = status.HTTP_403_FORBIDDEN
    code = "FORBIDDEN"


# ─── 404 Not Found ────────────────────────────────────────────────────────────

class NotFoundException(AppException):
    status_code = status.HTTP_404_NOT_FOUND
    code = "NOT_FOUND"


class DocumentNotFoundException(NotFoundException):
    code = "DOCUMENT_NOT_FOUND"


class ProductNotFoundException(NotFoundException):
    code = "PRODUCT_NOT_FOUND"


# ─── 429 Rate Limit ───────────────────────────────────────────────────────────

class RateLimitException(AppException):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    code = "RATE_LIMIT_EXCEEDED"


# ─── 500 Service Errors ───────────────────────────────────────────────────────

class LLMException(AppException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    code = "LLM_ERROR"


class AgentTimeoutException(AppException):
    status_code = status.HTTP_504_GATEWAY_TIMEOUT
    code = "AGENT_TIMEOUT"


class StorageException(AppException):
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    code = "STORAGE_ERROR"


# ─── Response builder ─────────────────────────────────────────────────────────

def _error_response(
    request: Request,
    status_code: int,
    code: str,
    message: str,
    detail: Any = None,
) -> JSONResponse:
    request_id = str(uuid.uuid4())
    body: dict[str, Any] = {
        "error": {
            "code": code,
            "message": message,
            "request_id": request_id,
        }
    }
    if detail is not None:
        body["error"]["detail"] = detail
    return JSONResponse(status_code=status_code, content=body)


# ─── FastAPI handlers ─────────────────────────────────────────────────────────

def register_exception_handlers(app: FastAPI) -> None:
    """Call this in app/main.py after creating the FastAPI instance."""

    @app.exception_handler(AppException)
    async def app_exception_handler(
        request: Request, exc: AppException
    ) -> JSONResponse:
        logger.warning(
            "request.error",
            code=exc.code,
            message=exc.message,
            path=request.url.path,
            method=request.method,
        )
        return _error_response(
            request, exc.status_code, exc.code, exc.message, exc.detail
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        logger.error(
            "request.unhandled_error",
            path=request.url.path,
            method=request.method,
            error=str(exc),
            traceback=traceback.format_exc(),
        )
        return _error_response(
            request,
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "INTERNAL_ERROR",
            "An unexpected error occurred. Our team has been notified.",
        )
