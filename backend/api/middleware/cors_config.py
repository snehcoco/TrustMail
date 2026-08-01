"""
CORS Configuration
==================
Configures permissive-yet-safe CORS for the TrustMail API.
By default only allows localhost origins and Chrome extensions.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from config.settings import Settings


def configure_cors(app: FastAPI, settings: Settings) -> None:
    """Add CORSMiddleware with settings-driven allowed origins."""
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_origin_regex=r"chrome-extension://.*",  # Allow any extension ID
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "Accept", "X-Request-ID"],
        max_age=600,
    )
