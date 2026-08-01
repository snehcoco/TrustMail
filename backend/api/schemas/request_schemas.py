"""
Pydantic Request Schemas
=========================
All input validation for TrustMail API endpoints.
Using strict Pydantic v2 models with detailed field validation.
"""

from __future__ import annotations

from typing import Dict, List, Optional
from pydantic import BaseModel, Field, field_validator, model_validator
import re


# ─────────────────────────────────────────────────────────────────────────────
# Shared sub-models
# ─────────────────────────────────────────────────────────────────────────────

class EmailHeaders(BaseModel):
    """Parsed email headers for analysis."""
    received: Optional[List[str]] = Field(default=None, description="Received chain")
    from_: Optional[str] = Field(default=None, alias="from", description="From header")
    reply_to: Optional[str] = Field(default=None, description="Reply-To header")
    return_path: Optional[str] = Field(default=None, description="Return-Path header")
    message_id: Optional[str] = Field(default=None, description="Message-ID")
    date: Optional[str] = Field(default=None, description="Date header")
    spf: Optional[str] = Field(default=None, description="SPF authentication result")
    dkim: Optional[str] = Field(default=None, description="DKIM authentication result")
    dmarc: Optional[str] = Field(default=None, description="DMARC policy result")
    x_mailer: Optional[str] = Field(default=None, description="X-Mailer header")
    x_originating_ip: Optional[str] = Field(default=None, description="X-Originating-IP")
    authentication_results: Optional[str] = Field(default=None, description="Authentication-Results")
    raw: Optional[str] = Field(default=None, description="Full raw headers string")

    class Config:
        populate_by_name = True


class AttachmentMetadata(BaseModel):
    """Metadata about an email attachment."""
    filename: str = Field(..., description="Filename of the attachment")
    mime_type: Optional[str] = Field(default=None, description="MIME type")
    size_bytes: Optional[int] = Field(default=None, ge=0, description="File size in bytes")
    extension: Optional[str] = Field(default=None, description="File extension")
    is_executable: Optional[bool] = Field(default=None, description="Whether extension is executable")

    @field_validator("filename")
    @classmethod
    def sanitize_filename(cls, v: str) -> str:
        # Strip path traversal characters
        return re.sub(r"[/\\<>:\"'|?*]", "_", v)


# ─────────────────────────────────────────────────────────────────────────────
# /analyze — Single email analysis
# ─────────────────────────────────────────────────────────────────────────────

class AnalyzeRequest(BaseModel):
    """Full email analysis request."""

    # Content
    subject: Optional[str] = Field(default=None, max_length=1000)
    body_text: Optional[str] = Field(default=None, max_length=50_000, description="Plain-text body")
    body_html: Optional[str] = Field(default=None, max_length=200_000, description="HTML body")

    # Sender information
    sender: Optional[str] = Field(default=None, max_length=500)
    sender_domain: Optional[str] = Field(default=None, max_length=253)
    reply_to: Optional[str] = Field(default=None, max_length=500)
    return_path: Optional[str] = Field(default=None, max_length=500)

    # Extracted artefacts
    urls: Optional[List[str]] = Field(default=None, max_length=200)
    attachments: Optional[List[AttachmentMetadata]] = Field(default=None)
    headers: Optional[EmailHeaders] = Field(default=None)

    # Metadata
    email_id: Optional[str] = Field(default=None, description="Client-side ID for tracking")
    platform: Optional[str] = Field(default=None, description="Email platform (gmail, outlook, etc.)")
    include_explanation: bool = Field(default=True, description="Include SHAP/LIME explanation")

    @model_validator(mode="after")
    def require_at_least_one_field(self) -> "AnalyzeRequest":
        if not any([self.subject, self.body_text, self.body_html, self.sender]):
            raise ValueError("At least one of subject, body_text, body_html, or sender must be provided.")
        return self


# ─────────────────────────────────────────────────────────────────────────────
# /batch — Multiple emails
# ─────────────────────────────────────────────────────────────────────────────

class BatchAnalyzeRequest(BaseModel):
    """Batch analysis of multiple emails."""
    emails: List[AnalyzeRequest] = Field(..., min_length=1, max_length=50)
    include_explanation: bool = Field(default=False, description="Include explanations (slower)")


# ─────────────────────────────────────────────────────────────────────────────
# /headers — Headers-only analysis
# ─────────────────────────────────────────────────────────────────────────────

class HeaderAnalyzeRequest(BaseModel):
    """Analyze only email headers."""
    headers: EmailHeaders = Field(..., description="Parsed email headers")
    raw_headers: Optional[str] = Field(default=None, max_length=50_000, description="Raw headers string")


# ─────────────────────────────────────────────────────────────────────────────
# /urls — URL analysis
# ─────────────────────────────────────────────────────────────────────────────

class URLAnalyzeRequest(BaseModel):
    """Analyze a list of URLs from an email."""
    urls: List[str] = Field(..., min_length=1, max_length=100)
    context: Optional[str] = Field(default=None, max_length=500, description="Surrounding text context")

    @field_validator("urls")
    @classmethod
    def validate_urls(cls, urls: List[str]) -> List[str]:
        cleaned = []
        for url in urls:
            url = url.strip()
            if len(url) > 2048:
                raise ValueError(f"URL exceeds maximum length: {url[:50]}...")
            cleaned.append(url)
        return cleaned


# ─────────────────────────────────────────────────────────────────────────────
# /attachments — Attachment analysis
# ─────────────────────────────────────────────────────────────────────────────

class AttachmentAnalyzeRequest(BaseModel):
    """Analyze attachment metadata."""
    attachments: List[AttachmentMetadata] = Field(..., min_length=1, max_length=50)
    email_context: Optional[str] = Field(default=None, max_length=2000, description="Email subject/body snippet")


# ─────────────────────────────────────────────────────────────────────────────
# /explain — Explanation request
# ─────────────────────────────────────────────────────────────────────────────

class ExplainRequest(BaseModel):
    """Request detailed explainability for an email."""
    email: AnalyzeRequest
    explanation_methods: List[str] = Field(
        default=["shap", "lime"],
        description="Which explainability methods to run"
    )

    @field_validator("explanation_methods")
    @classmethod
    def validate_methods(cls, methods: List[str]) -> List[str]:
        valid = {"shap", "lime", "attention", "feature_importance"}
        invalid = set(methods) - valid
        if invalid:
            raise ValueError(f"Invalid explanation methods: {invalid}. Valid: {valid}")
        return methods
