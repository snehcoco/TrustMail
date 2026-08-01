"""
POST /api/v1/explain — Detailed Explainability
================================================
Returns a deep SHAP + LIME + feature importance explanation
for a given email, without re-running inference if already cached.
"""

import time

from fastapi import APIRouter, Request, HTTPException
from loguru import logger

from api.schemas.request_schemas import ExplainRequest
from api.schemas.response_schemas import ExplainResponse
from api.services.email_analyzer import EmailAnalyzer
from api.explainability.shap_explainer import SHAPExplainer
from api.explainability.lime_explainer import LIMEExplainer

router = APIRouter()


@router.post(
    "/explain",
    response_model=ExplainResponse,
    summary="Get detailed explainability for an email",
    description=(
        "Runs SHAP, LIME, and/or attention visualization on the email "
        "to produce a detailed, human-readable explanation of the model's prediction. "
        "Slower than /analyze — use for detailed investigation."
    ),
)
async def explain_email(request_body: ExplainRequest, request: Request) -> ExplainResponse:
    """
    Deep explainability endpoint.
    Runs SHAP + LIME on the feature vector extracted from the email.
    """
    start_ts = time.perf_counter()

    try:
        loader = request.app.state.model_loader
        analyzer = EmailAnalyzer(model_loader=loader)

        # Run base analysis to get features and prediction
        base_result = await analyzer.analyze(request_body.email)

        response = ExplainResponse(
            email_id=request_body.email.email_id,
            risk_level=base_result.risk_level,
            risk_score=base_result.risk_score,
            shap_explanation=base_result.shap_explanation,
            lime_explanation=base_result.lime_explanation,
            top_reasons=base_result.top_reasons,
        )

        # Run attention visualization if requested and available
        if "attention" in request_body.explanation_methods:
            try:
                from api.explainability.attention_visualizer import AttentionVisualizer
                vis = AttentionVisualizer(loader)
                response.attention_highlights = vis.get_highlights(request_body.email)
            except Exception as attn_err:
                logger.warning(f"Attention visualization skipped: {attn_err}")

        elapsed_ms = int((time.perf_counter() - start_ts) * 1000)
        logger.info(f"[explain] duration={elapsed_ms}ms methods={request_body.explanation_methods}")
        return response

    except Exception as exc:
        logger.exception(f"Explanation error: {exc}")
        raise HTTPException(status_code=500, detail="Explanation failed") from exc
