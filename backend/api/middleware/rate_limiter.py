"""
Rate Limiting Middleware
========================
Sliding-window token-bucket rate limiter.
Uses in-memory storage (suitable for single-process deployment).
For multi-process deployments, replace with Redis-backed implementation.
"""

import time
from collections import defaultdict, deque
from typing import Deque, Dict

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Per-IP sliding-window rate limiter.

    Args:
        requests: Maximum requests allowed in the window.
        window: Time window in seconds.
    """

    def __init__(self, app, requests: int = 60, window: int = 60) -> None:
        super().__init__(app)
        self.max_requests = requests
        self.window_seconds = window
        # IP -> deque of timestamps
        self._buckets: Dict[str, Deque[float]] = defaultdict(deque)

    def _get_client_ip(self, request: Request) -> str:
        """Extract real client IP, respecting common proxy headers."""
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    async def dispatch(self, request: Request, call_next) -> Response:
        # Skip rate limiting for health checks to allow monitoring tools
        if request.url.path in ("/health", "/docs", "/openapi.json", "/redoc"):
            return await call_next(request)

        client_ip = self._get_client_ip(request)
        now = time.monotonic()
        window_start = now - self.window_seconds

        bucket = self._buckets[client_ip]

        # Remove timestamps outside the current window
        while bucket and bucket[0] < window_start:
            bucket.popleft()

        if len(bucket) >= self.max_requests:
            retry_after = int(self.window_seconds - (now - bucket[0]))
            return JSONResponse(
                status_code=429,
                content={
                    "error": "Rate limit exceeded",
                    "retry_after_seconds": retry_after,
                },
                headers={"Retry-After": str(retry_after)},
            )

        bucket.append(now)
        response = await call_next(request)

        # Attach rate limit headers
        remaining = self.max_requests - len(bucket)
        response.headers["X-RateLimit-Limit"] = str(self.max_requests)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Window"] = str(self.window_seconds)

        return response
