"""
Audit Logging Middleware
========================
Logs every API request/response for security audit purposes.
Raw email content is NEVER logged — only metadata.
Complies with the TrustMail privacy policy.
"""

import time
import uuid

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from loguru import logger


class AuditLogMiddleware(BaseHTTPMiddleware):
    """
    Non-invasive audit middleware.

    Logs:
      - Request method, path, client IP
      - Response status code, latency
      - Request ID (UUID4) for correlation

    Does NOT log:
      - Request or response bodies (email content)
      - Any PII from emails
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = str(uuid.uuid4())[:8]
        client_ip = (request.client.host if request.client else "unknown")
        start = time.perf_counter()

        # Inject request ID into request state for downstream use
        request.state.request_id = request_id

        response = await call_next(request)

        elapsed_ms = int((time.perf_counter() - start) * 1000)

        logger.info(
            f"[audit] id={request_id} method={request.method} "
            f"path={request.url.path} ip={client_ip} "
            f"status={response.status_code} duration={elapsed_ms}ms"
        )

        response.headers["X-Request-ID"] = request_id
        return response
