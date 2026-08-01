"""
POST /api/v1/batch — Batch Email Analysis
==========================================
Analyze multiple emails in a single request.
Uses async concurrency with a semaphore to prevent resource exhaustion.
"""

import asyncio
import time

from fastapi import APIRouter, Request, HTTPException
from loguru import logger

from api.schemas.request_schemas import BatchAnalyzeRequest
from api.schemas.response_schemas import BatchAnalyzeResponse, AnalyzeResponse, RiskLevel
from api.services.email_analyzer import EmailAnalyzer
from api.routes.health import increment_counter, record_latency

router = APIRouter()

# Limit concurrency to avoid memory pressure with large batches
_SEMAPHORE = asyncio.Semaphore(4)


@router.post(
    "/batch",
    response_model=BatchAnalyzeResponse,
    summary="Analyze multiple emails",
    description="Analyze up to 50 emails in a single request. Explanations are optional and slow; disable for speed.",
)
async def batch_analyze(request_body: BatchAnalyzeRequest, request: Request) -> BatchAnalyzeResponse:
    """
    Batch analysis with async concurrency control.
    Each email is analyzed independently; errors in one do not fail others.
    """
    start_ts = time.perf_counter()
    increment_counter("total_requests")
    increment_counter("total_analyzed", len(request_body.emails))

    analyzer = EmailAnalyzer(model_loader=request.app.state.model_loader)

    async def analyze_one(email_req) -> AnalyzeResponse:
        async with _SEMAPHORE:
            return await analyzer.analyze(email_req)

    tasks = [analyze_one(email) for email in request_body.emails]
    results: list[AnalyzeResponse | Exception] = await asyncio.gather(*tasks, return_exceptions=True)

    # Replace exceptions with error-state responses
    final_results: list[AnalyzeResponse] = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            logger.error(f"Batch item {i} failed: {result}")
            final_results.append(
                AnalyzeResponse(
                    risk_level=RiskLevel.SUSPICIOUS,
                    risk_score=0.5,
                    confidence=0.0,
                    top_reasons=["Analysis failed for this email"],
                )
            )
        else:
            final_results.append(result)

    elapsed_ms = int((time.perf_counter() - start_ts) * 1000)
    record_latency(elapsed_ms)

    high_risk = sum(1 for r in final_results if r.risk_score >= 0.65)

    return BatchAnalyzeResponse(
        results=final_results,
        total_analyzed=len(final_results),
        total_duration_ms=elapsed_ms,
        high_risk_count=high_risk,
    )
