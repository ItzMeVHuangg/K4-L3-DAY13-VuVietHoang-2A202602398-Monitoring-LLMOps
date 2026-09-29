from __future__ import annotations

import time
import uuid

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from structlog.contextvars import bind_contextvars, clear_contextvars


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Clear contextvars from any previous request handled on this worker
        # so correlation_id / user context never leaks across requests.
        clear_contextvars()

        # Reuse an inbound x-request-id if present, otherwise mint a new one
        # in the req-<8-char-hex> format.
        correlation_id = request.headers.get("x-request-id") or f"req-{uuid.uuid4().hex[:8]}"

        # Bind so every structlog call during this request automatically
        # includes correlation_id without passing it explicitly each time.
        bind_contextvars(correlation_id=correlation_id)

        request.state.correlation_id = correlation_id

        start = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = int((time.perf_counter() - start) * 1000)

        # Echo the correlation_id and timing back to the caller so it can be
        # matched against the structured logs for this same request.
        response.headers["x-request-id"] = correlation_id
        response.headers["x-response-time-ms"] = str(elapsed_ms)

        return response
