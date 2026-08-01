"""
POST /api/v1/analyze — Single Email Analysis
=============================================
The primary endpoint. Accepts an email's content, headers, and metadata,
runs the full hybrid AI pipeline, and returns a rich threat assessment.
"""

import time
from datetime import datetime, timezone

from fastapi import APIRouter, Request, HTTPException
from loguru import logger

from api.schemas.request_schemas import AnalyzeRequest
from api.schemas.response_schemas import AnalyzeResponse
from api.services.email_analyzer import EmailAnalyzer
from api.routes.health import increment_counter, record_latency

router = APIRouter()


@router.post(
    "/analyze",
    response_model=AnalyzeResponse,
    summary="Analyze a single email for threats",
    description=(
        "Runs the full TrustMail hybrid AI pipeline on a single email. "
        "Returns risk level, confidence, threat categories, header findings, "
        "URL findings, NLP findings, and optional SHAP/LIME explanations."
    ),
)
async def analyze_email(request_body: AnalyzeRequest, request: Request) -> AnalyzeResponse:
    """
    Full email analysis pipeline:
    1. Feature extraction (TF-IDF, n-grams, stylometry, URL/header features)
    2. Classical model ensemble (RF, XGBoost, LightGBM, CatBoost, LR)
    3. Ensemble stacking with calibrated probabilities
    4. SHAP + LIME explanation generation (if requested)
    """
    start_ts = time.perf_counter()
    increment_counter("total_requests")
    increment_counter("total_analyzed")

    try:
        analyzer = EmailAnalyzer(model_loader=request.app.state.model_loader)
        result = await analyzer.analyze(request_body)

        # Attach timing and timestamp
        elapsed_ms = int((time.perf_counter() - start_ts) * 1000)
        result.scan_duration_ms = elapsed_ms
        result.analysis_timestamp = datetime.now(timezone.utc).isoformat()

        record_latency(elapsed_ms)

        # Track phishing detections for metrics
        if result.risk_score >= 0.65:
            increment_counter("phishing_detected")

        logger.info(
            f"[analyze] risk={result.risk_level} score={result.risk_score:.3f} "
            f"confidence={result.confidence:.3f} duration={elapsed_ms}ms"
        )
        return result

    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception(f"Error analyzing email: {exc}")
        raise HTTPException(status_code=500, detail="Analysis failed") from exc
