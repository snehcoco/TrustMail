"""
TrustMail FastAPI Application Factory
======================================
Creates the configured FastAPI app instance with:
  - All route registrations
  - Middleware stack (CORS, rate limiting, audit logging)
  - Startup/shutdown lifespan for model preloading
  - OpenAPI docs
"""

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from loguru import logger

from config.settings import get_settings
from api.middleware.cors_config import configure_cors
from api.middleware.rate_limiter import RateLimitMiddleware
from api.middleware.audit_logger import AuditLogMiddleware
from api.routes import analyze, batch, headers, urls, attachments, explain, health
from inference.model_loader import ModelLoader


# ─────────────────────────────────────────────────────────────────────────────
# Lifespan — preload models on startup, release on shutdown
# ─────────────────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """
    ASGI lifespan handler.
    Classical ML models are loaded once at startup and stored in app.state.
    This avoids cold-start latency on first request.
    """
    settings = get_settings()
    logger.info("⚙️  Loading TrustMail classical ensemble models...")

    loader = ModelLoader(settings)
    app.state.model_loader = loader
    loader.load_all()

    mode = "full AI" if loader.has_trained_models() else "heuristic fallback"
    logger.info(f"✅ TrustMail backend ready — mode: {mode}")
    logger.info(f"📍 API docs at http://{settings.HOST}:{settings.PORT}/docs")

    yield  # Application runs here

    logger.info("🛑 Shutting down TrustMail backend...")
    loader.unload_all()



# ─────────────────────────────────────────────────────────────────────────────
# Application Factory
# ─────────────────────────────────────────────────────────────────────────────

def create_app() -> FastAPI:
    """
    Factory function that creates and configures the FastAPI application.
    Called by uvicorn when using factory=True in app.py.
    """
    settings = get_settings()

    app = FastAPI(
        title=settings.API_TITLE,
        description=settings.API_DESCRIPTION,
        version=settings.API_VERSION,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    # ── Middleware (order matters — outermost applied last) ─────────────────
    configure_cors(app, settings)
    app.add_middleware(GZipMiddleware, minimum_size=1000)
    app.add_middleware(AuditLogMiddleware)
    if settings.RATE_LIMIT_ENABLED:
        app.add_middleware(
            RateLimitMiddleware,
            requests=settings.RATE_LIMIT_REQUESTS,
            window=settings.RATE_LIMIT_WINDOW,
        )

    # ── Routes ──────────────────────────────────────────────────────────────
    prefix = settings.API_PREFIX
    app.include_router(health.router, tags=["System"])
    app.include_router(analyze.router, prefix=prefix, tags=["Analysis"])
    app.include_router(batch.router, prefix=prefix, tags=["Analysis"])
    app.include_router(headers.router, prefix=prefix, tags=["Analysis"])
    app.include_router(urls.router, prefix=prefix, tags=["Analysis"])
    app.include_router(attachments.router, prefix=prefix, tags=["Analysis"])
    app.include_router(explain.router, prefix=prefix, tags=["Explainability"])

    # ── Global exception handler ────────────────────────────────────────────
    @app.exception_handler(Exception)
    async def global_exception_handler(request, exc):  # type: ignore[no-untyped-def]
        logger.exception(f"Unhandled exception: {exc}")
        return JSONResponse(
            status_code=500,
            content={"error": "Internal server error", "detail": str(exc)},
        )

    # ── Root route: redirect / → /docs so browser gets a useful page ───────
    @app.get("/", include_in_schema=False)
    async def root():
        """Redirects the browser to the interactive API documentation."""
        return RedirectResponse(url="/docs")

    return app
