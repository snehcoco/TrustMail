"""
Pydantic Response Schemas
==========================
All output models for TrustMail API responses.
Every prediction includes a rich explanation structure.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


# ─────────────────────────────────────────────────────────────────────────────
# Enums
# ─────────────────────────────────────────────────────────────────────────────

class RiskLevel(str, Enum):
    SAFE = "safe"
    LOW_RISK = "low_risk"
    SUSPICIOUS = "suspicious"
    PHISHING = "phishing"
    HIGHLY_DANGEROUS = "highly_dangerous"


class ThreatCategory(str, Enum):
    CREDENTIAL_HARVESTING = "credential_harvesting"
    CEO_FRAUD = "ceo_fraud"
    BEC = "business_email_compromise"
    FAKE_INVOICE = "fake_invoice"
    PASSWORD_RESET_SCAM = "password_reset_scam"
    CRYPTO_SCAM = "cryptocurrency_scam"
    FAKE_TAX = "fake_tax_notice"
    FAKE_DELIVERY = "fake_package_delivery"
    BANKING_FRAUD = "banking_fraud"
    ACCOUNT_VERIFICATION = "account_verification_scam"
    FAKE_LOGIN = "fake_login_page"
    IMPERSONATION = "impersonation"
    MALWARE_ATTACHMENT = "malware_attachment"
    SPAM = "spam"
    UNKNOWN = "unknown"


# ─────────────────────────────────────────────────────────────────────────────
# Sub-response models
# ─────────────────────────────────────────────────────────────────────────────

class FeatureImportanceItem(BaseModel):
    feature: str = Field(..., description="Feature name")
    importance: float = Field(..., description="Importance score [-1, 1]")
    direction: str = Field(..., description="'phishing' or 'safe'")


class SHAPExplanation(BaseModel):
    top_features: List[FeatureImportanceItem]
    base_value: float = Field(..., description="SHAP base value (model bias)")
    expected_value: float
    shap_values_summary: Optional[Dict[str, float]] = None


class LIMEExplanation(BaseModel):
    top_features: List[FeatureImportanceItem]
    intercept: float
    local_prediction: float
    score: float = Field(..., description="LIME fidelity score")


class HeaderFinding(BaseModel):
    check: str = Field(..., description="Check name (e.g. SPF, DKIM)")
    result: str = Field(..., description="Pass / Fail / Missing / Suspicious")
    severity: str = Field(..., description="critical / high / medium / low / info")
    detail: Optional[str] = None
    score_contribution: int = Field(..., description="Points added to risk score")


class URLFinding(BaseModel):
    url: str
    risk_score: float = Field(..., ge=0.0, le=1.0)
    threats: List[str] = Field(default_factory=list, description="Detected threat types")
    is_shortened: bool = False
    is_ip_based: bool = False
    is_homograph: bool = False
    is_typosquatting: bool = False
    suspicious_tld: bool = False
    redirect_depth: int = 0
    decoded_url: Optional[str] = None


class AttachmentFinding(BaseModel):
    filename: str
    risk_score: float = Field(..., ge=0.0, le=1.0)
    is_executable: bool = False
    is_double_extension: bool = False
    is_suspicious_type: bool = False
    threats: List[str] = Field(default_factory=list)


class NLPFinding(BaseModel):
    category: str = Field(..., description="NLP threat category detected")
    confidence: float = Field(..., ge=0.0, le=1.0)
    matched_phrases: List[str] = Field(default_factory=list)
    score_contribution: int


class ModelPrediction(BaseModel):
    """Individual sub-model prediction."""
    model_name: str
    phishing_probability: float = Field(..., ge=0.0, le=1.0)
    weight: float = Field(..., description="Ensemble weight")
    weighted_contribution: float


# ─────────────────────────────────────────────────────────────────────────────
# Primary analysis response
# ─────────────────────────────────────────────────────────────────────────────

class AnalyzeResponse(BaseModel):
    """Complete analysis result for a single email."""

    # ── Classification ──────────────────────────────────────────────────────
    risk_level: RiskLevel
    risk_score: float = Field(..., ge=0.0, le=1.0, description="Overall risk [0,1]")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Ensemble confidence")
    threat_categories: List[ThreatCategory] = Field(default_factory=list)

    # ── Sub-analyses ─────────────────────────────────────────────────────────
    header_findings: List[HeaderFinding] = Field(default_factory=list)
    url_findings: List[URLFinding] = Field(default_factory=list)
    attachment_findings: List[AttachmentFinding] = Field(default_factory=list)
    nlp_findings: List[NLPFinding] = Field(default_factory=list)

    # ── Explainability ───────────────────────────────────────────────────────
    shap_explanation: Optional[SHAPExplanation] = None
    lime_explanation: Optional[LIMEExplanation] = None
    top_reasons: List[str] = Field(default_factory=list, description="Human-readable top reasons")
    suspicious_keywords: List[str] = Field(default_factory=list)

    # ── Model ensemble breakdown ─────────────────────────────────────────────
    model_predictions: List[ModelPrediction] = Field(default_factory=list)

    # ── Sender / domain ──────────────────────────────────────────────────────
    sender_domain_age_days: Optional[int] = None
    sender_domain_suspicious: bool = False
    reply_to_mismatch: bool = False

    # ── Metadata ─────────────────────────────────────────────────────────────
    email_id: Optional[str] = None
    scan_duration_ms: Optional[int] = None
    model_version: str = "1.0.0"
    analysis_timestamp: Optional[str] = None


# ─────────────────────────────────────────────────────────────────────────────
# Batch response
# ─────────────────────────────────────────────────────────────────────────────

class BatchAnalyzeResponse(BaseModel):
    results: List[AnalyzeResponse]
    total_analyzed: int
    total_duration_ms: int
    high_risk_count: int


# ─────────────────────────────────────────────────────────────────────────────
# Headers-only response
# ─────────────────────────────────────────────────────────────────────────────

class HeaderAnalyzeResponse(BaseModel):
    risk_score: float = Field(..., ge=0.0, le=1.0)
    risk_level: RiskLevel
    findings: List[HeaderFinding]
    spf_pass: Optional[bool] = None
    dkim_pass: Optional[bool] = None
    dmarc_pass: Optional[bool] = None
    reply_to_mismatch: bool = False
    summary: str


# ─────────────────────────────────────────────────────────────────────────────
# URL-only response
# ─────────────────────────────────────────────────────────────────────────────

class URLAnalyzeResponse(BaseModel):
    urls_analyzed: int
    high_risk_urls: int
    findings: List[URLFinding]
    overall_risk_score: float = Field(..., ge=0.0, le=1.0)


# ─────────────────────────────────────────────────────────────────────────────
# Attachment-only response
# ─────────────────────────────────────────────────────────────────────────────

class AttachmentAnalyzeResponse(BaseModel):
    attachments_analyzed: int
    high_risk_count: int
    findings: List[AttachmentFinding]
    overall_risk_score: float = Field(..., ge=0.0, le=1.0)


# ─────────────────────────────────────────────────────────────────────────────
# Explain response
# ─────────────────────────────────────────────────────────────────────────────

class ExplainResponse(BaseModel):
    email_id: Optional[str] = None
    risk_level: RiskLevel
    risk_score: float
    shap_explanation: Optional[SHAPExplanation] = None
    lime_explanation: Optional[LIMEExplanation] = None
    feature_importance: List[FeatureImportanceItem] = Field(default_factory=list)
    attention_highlights: Optional[List[Dict[str, Any]]] = None
    top_reasons: List[str] = Field(default_factory=list)


# ─────────────────────────────────────────────────────────────────────────────
# System responses
# ─────────────────────────────────────────────────────────────────────────────

class HealthResponse(BaseModel):
    status: str
    version: str
    models_loaded: bool
    uptime_seconds: float


class VersionResponse(BaseModel):
    api_version: str
    model_version: str
    python_version: str


class MetricsResponse(BaseModel):
    total_requests: int
    total_analyzed: int
    avg_latency_ms: float
    p95_latency_ms: float
    phishing_detected: int
    false_positive_rate_estimated: float


class StatusResponse(BaseModel):
    models_loaded: Dict[str, bool]
    model_versions: Dict[str, str]
    memory_usage_mb: float
