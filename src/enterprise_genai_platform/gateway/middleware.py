"""HTTP security and resilience middleware."""

import asyncio
import logging
import re
import time
from collections.abc import Awaitable, Callable
from uuid import uuid4

from fastapi import Request, Response, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from enterprise_genai_platform.metrics import HTTP_DURATION, HTTP_REQUESTS

RequestHandler = Callable[[Request], Awaitable[Response]]
_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
_KNOWN_METRIC_ROUTES = frozenset(
    {
        "/health/live",
        "/health/ready",
        "/metrics",
        "/api/v1/platform/info",
        "/api/v1/workflows/route",
        "/api/v1/workflows/investigate",
        "/api/v1/skills",
    }
)
logger = logging.getLogger(__name__)


class RequestSecurityMiddleware(BaseHTTPMiddleware):
    """Apply correlation, timeout, body-size, headers, and safe request logging."""

    def __init__(self, app: ASGIApp, *, max_body_bytes: int, timeout_seconds: float) -> None:
        super().__init__(app)
        self.max_body_bytes = max_body_bytes
        self.timeout_seconds = timeout_seconds

    async def dispatch(self, request: Request, call_next: RequestHandler) -> Response:
        request_id_header = request.headers.get("X-Request-ID", "")
        request_id = (
            request_id_header if _REQUEST_ID_PATTERN.fullmatch(request_id_header) else str(uuid4())
        )
        request.state.request_id = request_id

        content_length = request.headers.get("content-length")
        if content_length and self._body_too_large(content_length):
            oversized_response = JSONResponse(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                content={"detail": "Request body exceeds the configured limit"},
            )
            return self._secure(oversized_response, request_id)

        started = time.perf_counter()
        response: Response
        try:
            async with asyncio.timeout(self.timeout_seconds):
                response = await call_next(request)
        except TimeoutError:
            response = JSONResponse(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                content={"detail": "Request processing timed out"},
            )

        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        metric_route = request.url.path if request.url.path in _KNOWN_METRIC_ROUTES else "unmatched"
        if metric_route != "/metrics":
            HTTP_REQUESTS.labels(request.method, metric_route, str(response.status_code)).inc()
            HTTP_DURATION.labels(request.method, metric_route).observe(duration_ms / 1000)
        logger.info(
            "request_completed",
            extra={
                "event_fields": {
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code,
                    "duration_ms": duration_ms,
                }
            },
        )
        return self._secure(response, request_id)

    def _body_too_large(self, content_length: str) -> bool:
        try:
            return int(content_length) > self.max_body_bytes
        except ValueError:
            return True

    @staticmethod
    def _secure(response: Response, request_id: str) -> Response:
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Cache-Control"] = "no-store"
        response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
        return response
