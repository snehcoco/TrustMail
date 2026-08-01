"""
POST /api/v1/attachments — Attachment Metadata Analysis
=========================================================
Analyze attachment metadata for dangerous file types, double extensions,
and social engineering patterns in filenames.
"""

from fastapi import APIRouter, Request, HTTPException
from loguru import logger

from api.schemas.request_schemas import AttachmentAnalyzeRequest
from api.schemas.response_schemas import AttachmentAnalyzeResponse, AttachmentFinding
from api.services.email_analyzer import AttachmentAnalyzerService

router = APIRouter()


@router.post(
    "/attachments",
    response_model=AttachmentAnalyzeResponse,
    summary="Analyze email attachment metadata",
    description=(
        "Evaluate attachment filenames, MIME types, extensions, and sizes "
        "for dangerous file types, double extensions, and social engineering."
    ),
)
async def analyze_attachments(
    request_body: AttachmentAnalyzeRequest, request: Request
) -> AttachmentAnalyzeResponse:
    """Attachment metadata analysis endpoint."""
    try:
        service = AttachmentAnalyzerService()
        findings: list[AttachmentFinding] = service.analyze_all(request_body.attachments)
        overall = max((f.risk_score for f in findings), default=0.0)
        high_risk = sum(1 for f in findings if f.risk_score >= 0.65)

        return AttachmentAnalyzeResponse(
            attachments_analyzed=len(findings),
            high_risk_count=high_risk,
            findings=findings,
            overall_risk_score=round(overall, 3),
        )
    except Exception as exc:
        logger.exception(f"Attachment analysis error: {exc}")
        raise HTTPException(status_code=500, detail="Attachment analysis failed") from exc
