"""
POST /api/v1/urls — URL Threat Analysis
========================================
Analyze URLs extracted from emails for homograph attacks,
typosquatting, IDN abuse, shortened URLs, IP-based URLs, etc.
"""

from fastapi import APIRouter, Request, HTTPException
from loguru import logger

from api.schemas.request_schemas import URLAnalyzeRequest
from api.schemas.response_schemas import URLAnalyzeResponse
from api.services.url_analyzer import URLAnalyzer

router = APIRouter()


@router.post(
    "/urls",
    response_model=URLAnalyzeResponse,
    summary="Analyze URLs from an email",
    description=(
        "Perform deep URL threat analysis including homograph detection, "
        "typosquatting similarity, shortened URL detection, IP-based URLs, "
        "suspicious TLDs, and encoded/obfuscated URLs."
    ),
)
async def analyze_urls(request_body: URLAnalyzeRequest, request: Request) -> URLAnalyzeResponse:
    """URL-focused analysis endpoint."""
    try:
        analyzer = URLAnalyzer()
        return await analyzer.analyze(request_body)
    except Exception as exc:
        logger.exception(f"URL analysis error: {exc}")
        raise HTTPException(status_code=500, detail="URL analysis failed") from exc
