"""
Health, Version, Metrics, Status Endpoints
==========================================
GET /health       — Liveness probe
GET /version      — Model + API version info
GET /metrics      — Runtime performance metrics
GET /status       — Loaded models status
"""

import os
import platform
import time
from datetime import datetime

try:
    import psutil
    _PSUTIL_AVAILABLE = True
except ImportError:
    _PSUTIL_AVAILABLE = False


from fastapi import APIRouter, Request
from loguru import logger

from api.schemas.response_schemas import (
    HealthResponse,
    VersionResponse,
    MetricsResponse,
    StatusResponse,
)
from config.settings import get_settings

router = APIRouter()
settings = get_settings()

# Track server start time for uptime calculation
_SERVER_START_TIME = time.time()

# Simple in-memory request counters (replace with Prometheus in production)
_request_counters: dict = {
    "total_requests": 0,
    "total_analyzed": 0,
    "phishing_detected": 0,
    "latencies_ms": [],
}


def increment_counter(key: str, value: int = 1) -> None:
    """Thread-safe-ish counter increment (single worker)."""
    _request_counters[key] = _request_counters.get(key, 0) + value


def record_latency(ms: float) -> None:
    """Record a latency sample (keep last 1000)."""
    _request_counters["latencies_ms"].append(ms)
    if len(_request_counters["latencies_ms"]) > 1000:
        _request_counters["latencies_ms"] = _request_counters["latencies_ms"][-1000:]


# ─────────────────────────────────────────────────────────────────────────────

@router.get("/health", response_model=HealthResponse, summary="Health check")
async def health_check(request: Request) -> HealthResponse:
    """Liveness probe. Returns 200 if the server is running."""
    models_loaded = False
    try:
        loader = request.app.state.model_loader
        models_loaded = loader.is_ready()
    except AttributeError:
        pass

    return HealthResponse(
        status="ok",
        version=settings.API_VERSION,
        models_loaded=models_loaded,
        uptime_seconds=round(time.time() - _SERVER_START_TIME, 2),
    )


@router.get("/version", response_model=VersionResponse, summary="API and model versions")
async def get_version(request: Request) -> VersionResponse:
    """Returns version information for the API and loaded models."""
    model_version = "1.0.0"
    try:
        loader = request.app.state.model_loader
        model_version = loader.get_model_version()
    except AttributeError:
        pass

    return VersionResponse(
        api_version=settings.API_VERSION,
        model_version=model_version,
        python_version=platform.python_version(),
    )


@router.get("/metrics", response_model=MetricsResponse, summary="Performance metrics")
async def get_metrics() -> MetricsResponse:
    """Returns runtime performance metrics collected since server start."""
    latencies = _request_counters.get("latencies_ms", [])
    avg_latency = sum(latencies) / len(latencies) if latencies else 0.0

    sorted_latencies = sorted(latencies)
    p95_idx = int(len(sorted_latencies) * 0.95)
    p95_latency = sorted_latencies[p95_idx] if sorted_latencies else 0.0

    return MetricsResponse(
        total_requests=_request_counters.get("total_requests", 0),
        total_analyzed=_request_counters.get("total_analyzed", 0),
        avg_latency_ms=round(avg_latency, 2),
        p95_latency_ms=round(p95_latency, 2),
        phishing_detected=_request_counters.get("phishing_detected", 0),
        false_positive_rate_estimated=0.02,  # Updated after evaluation
    )


@router.get("/status", response_model=StatusResponse, summary="Model loading status")
async def get_status(request: Request) -> StatusResponse:
    """Returns detailed status of all loaded models and system resources."""
    models_loaded: dict = {}
    model_versions: dict = {}

    try:
        loader = request.app.state.model_loader
        models_loaded = loader.get_loaded_models()
        model_versions = loader.get_model_versions()
    except AttributeError:
        logger.warning("Model loader not available yet")

    mem_mb = 0.0
    if _PSUTIL_AVAILABLE:
        process = psutil.Process(os.getpid())
        mem_mb = process.memory_info().rss / (1024 * 1024)

    return StatusResponse(
        models_loaded=models_loaded,
        model_versions=model_versions,
        memory_usage_mb=round(mem_mb, 2),
    )
