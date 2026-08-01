"""
TrustMail Logger
=================
Structured logging configuration using loguru.
"""

import sys
from loguru import logger
from config.settings import get_settings


def configure_logging() -> None:
    """Configure loguru logger for production use."""
    settings = get_settings()

    logger.remove()  # Remove default handler

    # Console logger
    logger.add(
        sys.stdout,
        level=settings.LOG_LEVEL,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{line}</cyan> | "
            "<level>{message}</level>"
        ),
        colorize=True,
    )

    # File logger (if configured)
    if settings.AUDIT_LOG_FILE:
        logger.add(
            settings.AUDIT_LOG_FILE,
            level="INFO",
            rotation="100 MB",
            retention="30 days",
            compression="gz",
            format="{time:ISO8601} | {level} | {name}:{line} | {message}",
            # Never log sensitive data
            filter=lambda record: "email_content" not in record["extra"],
        )
