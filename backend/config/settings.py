"""
TrustMail Settings
==================
All configuration via Pydantic BaseSettings.
Override via environment variables or a .env file.
"""

from functools import lru_cache
from typing import List, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application-wide configuration."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # ── Server ────────────────────────────────────────────────────────────────
    HOST: str = "127.0.0.1"
    PORT: int = 8000
    RELOAD: bool = False
    WORKERS: int = 1
    LOG_LEVEL: str = "INFO"

    # ── API ───────────────────────────────────────────────────────────────────
    API_TITLE: str = "TrustMail API"
    API_DESCRIPTION: str = "Privacy-first email threat detection — 100% local inference"
    API_VERSION: str = "1.0.0"
    API_PREFIX: str = "/api/v1"

    # ── CORS ──────────────────────────────────────────────────────────────────
    # Only allow local extension & localhost by default
    CORS_ORIGINS: List[str] = [
        "chrome-extension://*",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
    ]

    # ── Rate Limiting ─────────────────────────────────────────────────────────
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_REQUESTS: int = 60     # requests
    RATE_LIMIT_WINDOW: int = 60       # seconds

    # ── Models ────────────────────────────────────────────────────────────────
    MODELS_DIR: str = "trained_models"
    ONNX_MODEL_FILE: str = "distilbert_phishing.onnx"
    CLASSICAL_MODEL_FILE: str = "ensemble_classical.pkl"
    VECTORIZER_FILE: str = "tfidf_vectorizer.pkl"
    SCALER_FILE: str = "feature_scaler.pkl"
    LABEL_ENCODER_FILE: str = "label_encoder.pkl"

    # ── Inference ─────────────────────────────────────────────────────────────
    MAX_EMAIL_LENGTH: int = 10_000        # characters
    MAX_URLS_PER_EMAIL: int = 100
    ONNX_NUM_THREADS: int = 4
    BATCH_SIZE: int = 16

    # ── Explainability ────────────────────────────────────────────────────────
    SHAP_MAX_FEATURES: int = 20
    LIME_NUM_SAMPLES: int = 300
    EXPLAIN_TIMEOUT_SEC: int = 30

    # ── Security ──────────────────────────────────────────────────────────────
    SECRET_KEY: str = "change-me-in-production-use-env-var"
    AUDIT_LOG_FILE: Optional[str] = "logs/audit.log"

    # ── Privacy ───────────────────────────────────────────────────────────────
    ENABLE_TELEMETRY: bool = False
    LOG_EMAIL_CONTENT: bool = False     # NEVER log raw email content by default

    # ── MLflow ────────────────────────────────────────────────────────────────
    MLFLOW_TRACKING_URI: str = "mlruns"
    MLFLOW_EXPERIMENT_NAME: str = "trustmail-phishing-detection"


@lru_cache()
def get_settings() -> Settings:
    """Return a cached Settings singleton."""
    return Settings()
