"""
POST /api/v1/headers — Email Header Analysis
==============================================
Inspect email headers for SPF, DKIM, DMARC failures,
reply-to/return-path mismatches, and spoofing indicators.
"""

from fastapi import APIRouter, Request, HTTPException
from loguru import logger

from api.schemas.request_schemas import HeaderAnalyzeRequest
from api.schemas.response_schemas import HeaderAnalyzeResponse
from api.services.header_analyzer import HeaderAnalyzer

router = APIRouter()


@router.post(
    "/headers",
    response_model=HeaderAnalyzeResponse,
    summary="Analyze email headers",
    description=(
        "Inspect email authentication headers (SPF, DKIM, DMARC), "
        "reply-to/return-path mismatches, received chain anomalies, and spoofing indicators."
    ),
)
async def analyze_headers(request_body: HeaderAnalyzeRequest, request: Request) -> HeaderAnalyzeResponse:
    """Headers-only analysis — fast and lightweight."""
    try:
        analyzer = HeaderAnalyzer()
        return await analyzer.analyze(request_body)
    except Exception as exc:
        logger.exception(f"Header analysis error: {exc}")
        raise HTTPException(status_code=500, detail="Header analysis failed") from exc
