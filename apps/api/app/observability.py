"""Structured request logging with correlation identifiers."""

from __future__ import annotations

import json
import logging
import time
from contextvars import ContextVar
from uuid import uuid4

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

request_id_context: ContextVar[str] = ContextVar("request_id", default="-")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": request_id_context.get(),
        }
        for key in ("job_id", "investigation_id", "user_id", "connector_id"):
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging() -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.INFO)


_REQUEST_ID_RE = __import__("re").compile(r"[^A-Za-z0-9\-_]")


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        raw_id = request.headers.get("X-Request-ID", "")
        # Sanitize to alphanumeric + hyphen/underscore to prevent log injection
        # and response-header injection via crafted X-Request-ID values.
        sanitized = _REQUEST_ID_RE.sub("", raw_id)[:64]
        request_id = sanitized if sanitized else str(uuid4())
        token = request_id_context.set(request_id)
        started = time.perf_counter()
        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            logging.getLogger("osint.http").info(
                "request_completed",
                extra={"user_id": getattr(request.state, "user_id", None)},
                exc_info=False,
            )
            return response
        finally:
            logging.getLogger("osint.http").debug(
                "request_duration_ms=%.2f", (time.perf_counter() - started) * 1000
            )
            request_id_context.reset(token)
