"""
TrustMail Backend — Entry Point
================================
Start the server simply by running:

    cd backend
    python app.py

This will automatically launch FastAPI via uvicorn on http://127.0.0.1:8000.
No manual uvicorn command is needed.

Architecture:
    - FastAPI application with 10 REST endpoints
    - Lazy-loaded ONNX inference models
    - Hybrid classical + transformer ensemble
    - SHAP + LIME explainability on every prediction
    - Full middleware stack: CORS, rate limiting, audit logging
"""

import sys
import os

# Ensure the backend directory is on the path for all imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import uvicorn
from loguru import logger

from config.settings import get_settings


def main() -> None:
    """
    Application entry point.

    Starts the TrustMail FastAPI server on localhost.
    All configuration is read from environment variables or config/settings.py.
    """
    settings = get_settings()

    logger.info("═" * 60)
    logger.info("  🛡️  TrustMail Backend — Starting Up")
    logger.info("═" * 60)
    logger.info(f"  Host    : {settings.HOST}")
    logger.info(f"  Port    : {settings.PORT}")
    logger.info(f"  Reload  : {settings.RELOAD}")
    logger.info(f"  Workers : {settings.WORKERS}")
    logger.info(f"  Log     : {settings.LOG_LEVEL}")
    logger.info("═" * 60)

    uvicorn.run(
        "api.app:create_app",
        factory=True,
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.RELOAD,
        workers=settings.WORKERS if not settings.RELOAD else 1,
        log_level=settings.LOG_LEVEL.lower(),
        access_log=True,
    )


if __name__ == "__main__":
    main()
