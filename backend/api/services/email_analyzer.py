"""
Email Analyzer — Main Orchestration Service
============================================
Coordinates the full 4-stage AI pipeline:
  Stage 1: Feature extraction
  Stage 2: Classical model ensemble
  Stage 3: ONNX Transformer inference
  Stage 4: Ensemble stacking + calibration
  + SHAP/LIME explainability
"""

from __future__ import annotations

import re
import time
from typing import List, Optional, Tuple

import numpy as np
from loguru import logger

from api.schemas.request_schemas import AnalyzeRequest, AttachmentMetadata
from api.schemas.response_schemas import (
    AnalyzeResponse,
    AttachmentFinding,
    NLPFinding,
    RiskLevel,
    ThreatCategory,
)
from api.services.header_analyzer import HeaderAnalyzer
from api.services.url_analyzer import URLAnalyzer
from api.services.ensemble import EnsembleService
from preprocessing.feature_extractor import FeatureExtractor
from preprocessing.text_cleaner import TextCleaner
from api.explainability.shap_explainer import SHAPExplainer
from api.explainability.lime_explainer import LIMEExplainer
from config.settings import get_settings

# ── Dangerous file extensions ────────────────────────────────────────────────
DANGEROUS_EXTENSIONS = {
    ".exe", ".bat", ".cmd", ".com", ".ps1", ".vbs", ".js", ".jar",
    ".hta", ".scr", ".pif", ".reg", ".msi", ".dll", ".lnk", ".wsf",
    ".wsh", ".zip", ".rar", ".7z", ".iso", ".img",
}

# ── NLP threat pattern definitions ──────────────────────────────────────────
NLP_PATTERNS = {
    "urgency_language": {
        "phrases": [
            "act now", "urgent", "immediately", "within 24 hours",
            "account will be suspended", "limited time", "expire today",
            "last chance", "final notice", "action required",
        ],
        "weight": 10,
    },
    "credential_harvesting": {
        "phrases": [
            "enter your password", "verify your account", "confirm your credentials",
            "sign in to secure", "update payment", "billing information required",
            "confirm your identity", "validate your email",
        ],
        "weight": 25,
    },
    "fear_tactics": {
        "phrases": [
            "your account has been compromised", "suspicious activity",
            "unauthorized access", "we detected unusual", "your account will be deleted",
            "legal action", "law enforcement", "irs", "tax authority",
        ],
        "weight": 15,
    },
    "authority_abuse": {
        "phrases": [
            "ceo", "cfo", "president", "director", "management",
            "it department", "helpdesk", "microsoft security",
            "google security team", "apple support",
        ],
        "weight": 10,
    },
    "fake_login_page": {
        "phrases": [
            "click here to login", "verify here", "secure login",
            "account portal", "sign in below", "access your account",
        ],
        "weight": 20,
    },
    "social_engineering": {
        "phrases": [
            "confidential", "do not share", "between you and me",
            "wire transfer", "gift card", "itunes", "amazon gift",
            "western union", "bitcoin", "cryptocurrency payment",
        ],
        "weight": 15,
    },
}


class EmailAnalyzer:
    """
    Main email analysis orchestrator.

    Design: Stateless — receives a ModelLoader on construction,
    reuses loaded models from app.state without reloading.
    """

    def __init__(self, model_loader) -> None:
        self.model_loader = model_loader
        self.settings = get_settings()
        self.text_cleaner = TextCleaner()
        self.feature_extractor = FeatureExtractor()
        self.header_analyzer = HeaderAnalyzer()
        self.url_analyzer = URLAnalyzer()
        self.ensemble = EnsembleService(model_loader)

    async def analyze(self, request: AnalyzeRequest) -> AnalyzeResponse:
        """
        Full analysis pipeline. Returns a rich AnalyzeResponse.
        """
        # ── 1. Normalize inputs ──────────────────────────────────────────────
        text = self._build_text(request)
        clean_text = self.text_cleaner.clean(text)

        # ── 2. Header analysis ───────────────────────────────────────────────
        header_findings = []
        header_score = 0.0
        if request.headers:
            from api.schemas.request_schemas import HeaderAnalyzeRequest
            h_req = HeaderAnalyzeRequest(headers=request.headers)
            h_result = await self.header_analyzer.analyze(h_req)
            header_findings = h_result.findings
            header_score = h_result.risk_score

        # ── 3. URL analysis ──────────────────────────────────────────────────
        url_findings = []
        url_score = 0.0
        urls = request.urls or self._extract_urls(text)
        if urls:
            from api.schemas.request_schemas import URLAnalyzeRequest
            u_req = URLAnalyzeRequest(urls=urls[:self.settings.MAX_URLS_PER_EMAIL])
            u_result = await self.url_analyzer.analyze(u_req)
            url_findings = u_result.findings
            url_score = u_result.overall_risk_score

        # ── 4. Attachment analysis ───────────────────────────────────────────
        attachment_findings = []
        attachment_score = 0.0
        if request.attachments:
            svc = AttachmentAnalyzerService()
            attachment_findings = svc.analyze_all(request.attachments)
            if attachment_findings:
                attachment_score = max(f.risk_score for f in attachment_findings)

        # ── 5. NLP pattern analysis ──────────────────────────────────────────
        nlp_findings = self._run_nlp_patterns(text)
        nlp_score = min(sum(f.score_contribution for f in nlp_findings) / 100.0, 1.0)

        # ── 6. Feature extraction ────────────────────────────────────────────
        # Pass the fitted scaler so features match the training distribution.
        scaler = self.model_loader.get_scaler()
        features = self.feature_extractor.extract(
            text=clean_text,
            sender=request.sender,
            sender_domain=request.sender_domain,
            reply_to=request.reply_to,
            urls=urls,
            headers=request.headers,
            scaler=scaler,
        )

        # ── 7. Ensemble inference ────────────────────────────────────────────
        (
            ensemble_score,
            confidence,
            model_predictions,
        ) = self.ensemble.predict(features, clean_text)

        # ── 8. Combine all signals ───────────────────────────────────────────
        final_score = self._combine_scores(
            ensemble_score=ensemble_score,
            header_score=header_score,
            url_score=url_score,
            attachment_score=attachment_score,
            nlp_score=nlp_score,
        )

        # ── Confidence fallback ──────────────────────────────────────────────
        # When no ML models are loaded (heuristic mode), the ensemble returns
        # confidence=0.0. In this case, compute a proxy confidence from how
        # strongly the rule-based signals fire relative to the risk thresholds.
        # This gives the frontend a meaningful number instead of always 0%.
        if not model_predictions:
            # Heuristic confidence: distance from 0.5, scaled by signal strength
            # A final_score far from 0.5 means the rules agree strongly.
            confidence = round(abs(final_score - 0.5) * 2.0, 4)
            # Apply a conservative cap (heuristics are less reliable than models)
            confidence = min(confidence, 0.75)

        risk_level = self._score_to_level(final_score)
        threat_categories = self._detect_threat_categories(nlp_findings, url_findings, attachment_findings)
        top_reasons = self._build_reasons(header_findings, url_findings, nlp_findings, attachment_findings)
        suspicious_keywords = self._extract_suspicious_keywords(text)
        reply_to_mismatch = self._check_reply_to_mismatch(request)

        # ── 9. Explainability ────────────────────────────────────────────────
        shap_explanation = None
        lime_explanation = None

        if request.include_explanation:
            try:
                shap_exp = SHAPExplainer(self.model_loader)
                shap_explanation = shap_exp.explain(features)
            except Exception as e:
                logger.warning(f"SHAP failed: {e}")

            try:
                lime_exp = LIMEExplainer(self.model_loader)
                lime_explanation = lime_exp.explain(clean_text, features)
            except Exception as e:
                logger.warning(f"LIME failed: {e}")

        return AnalyzeResponse(
            risk_level=risk_level,
            risk_score=round(final_score, 4),
            confidence=round(confidence, 4),
            threat_categories=threat_categories,
            header_findings=header_findings,
            url_findings=url_findings,
            attachment_findings=attachment_findings,
            nlp_findings=nlp_findings,
            shap_explanation=shap_explanation,
            lime_explanation=lime_explanation,
            top_reasons=top_reasons,
            suspicious_keywords=suspicious_keywords,
            model_predictions=model_predictions,
            reply_to_mismatch=reply_to_mismatch,
            email_id=request.email_id,
            model_version=self.settings.API_VERSION,
        )


    # ── Private helpers ──────────────────────────────────────────────────────

    def _build_text(self, request: AnalyzeRequest) -> str:
        """Concatenate all text fields into a single string for analysis."""
        parts = []
        if request.subject:
            parts.append(f"SUBJECT: {request.subject}")
        if request.sender:
            parts.append(f"FROM: {request.sender}")
        if request.body_text:
            parts.append(request.body_text[: self.settings.MAX_EMAIL_LENGTH])
        elif request.body_html:
            # Strip HTML tags for text analysis
            html = request.body_html[: self.settings.MAX_EMAIL_LENGTH * 2]
            parts.append(re.sub(r"<[^>]+>", " ", html))
        return " ".join(parts)

    def _extract_urls(self, text: str) -> List[str]:
        """Extract URLs from text using a comprehensive regex."""
        url_pattern = re.compile(
            r"https?://[^\s<>\"']+|www\.[^\s<>\"']+"
            r"|(?:ftp|ftps)://[^\s<>\"']+",
            re.IGNORECASE,
        )
        return list(set(url_pattern.findall(text)))[:self.settings.MAX_URLS_PER_EMAIL]

    def _run_nlp_patterns(self, text: str) -> List[NLPFinding]:
        """Match NLP threat patterns against email text."""
        text_lower = text.lower()
        findings = []
        for category, config in NLP_PATTERNS.items():
            matched = [p for p in config["phrases"] if p in text_lower]
            if matched:
                confidence = min(len(matched) / max(len(config["phrases"]), 1) * 2, 1.0)
                findings.append(
                    NLPFinding(
                        category=category,
                        confidence=round(confidence, 3),
                        matched_phrases=matched[:10],
                        score_contribution=config["weight"],
                    )
                )
        return findings

    def _combine_scores(
        self,
        ensemble_score: float,
        header_score: float,
        url_score: float,
        attachment_score: float,
        nlp_score: float,
    ) -> float:
        """Weighted combination of all analysis signals."""
        # Ensemble model has highest weight; security signals boost the score
        combined = (
            ensemble_score * 0.50
            + header_score * 0.20
            + url_score * 0.15
            + attachment_score * 0.10
            + nlp_score * 0.05
        )
        return min(max(combined, 0.0), 1.0)

    def _score_to_level(self, score: float) -> RiskLevel:
        if score < 0.20:
            return RiskLevel.SAFE
        elif score < 0.45:
            return RiskLevel.LOW_RISK
        elif score < 0.65:
            return RiskLevel.SUSPICIOUS
        elif score < 0.85:
            return RiskLevel.PHISHING
        else:
            return RiskLevel.HIGHLY_DANGEROUS

    def _detect_threat_categories(self, nlp_findings, url_findings, attachment_findings) -> List[ThreatCategory]:
        categories = []
        nlp_cats = {f.category for f in nlp_findings}
        if "credential_harvesting" in nlp_cats or "fake_login_page" in nlp_cats:
            categories.append(ThreatCategory.CREDENTIAL_HARVESTING)
        if "social_engineering" in nlp_cats:
            categories.append(ThreatCategory.BEC)
        if "authority_abuse" in nlp_cats:
            categories.append(ThreatCategory.IMPERSONATION)
        if any(f.is_executable for f in attachment_findings):
            categories.append(ThreatCategory.MALWARE_ATTACHMENT)
        if any(f.is_shortened for f in url_findings):
            categories.append(ThreatCategory.FAKE_LOGIN)
        return list(set(categories))

    def _build_reasons(self, header_findings, url_findings, nlp_findings, attachment_findings) -> List[str]:
        reasons = []
        for h in header_findings:
            if h.result in ("Fail", "Missing"):
                reasons.append(f"✗ {h.check}: {h.result}")
        for u in url_findings[:3]:
            if u.risk_score > 0.5:
                reasons.extend(u.threats[:2])
        for n in nlp_findings[:3]:
            reasons.append(f"⚠ Detected {n.category.replace('_', ' ')}")
        for a in attachment_findings:
            if a.risk_score > 0.5:
                reasons.append(f"⚠ Suspicious attachment: {a.filename}")
        return reasons[:10]

    def _extract_suspicious_keywords(self, text: str) -> List[str]:
        all_phrases = []
        text_lower = text.lower()
        for config in NLP_PATTERNS.values():
            all_phrases.extend(p for p in config["phrases"] if p in text_lower)
        return list(set(all_phrases))[:20]

    def _check_reply_to_mismatch(self, request: AnalyzeRequest) -> bool:
        if request.reply_to and request.sender:
            def domain_of(email: str) -> str:
                match = re.search(r"@([\w.\-]+)", email)
                return match.group(1).lower() if match else ""
            return domain_of(request.reply_to) != domain_of(request.sender)
        return False


class AttachmentAnalyzerService:
    """Analyzes attachment metadata for risk indicators."""

    def analyze_all(self, attachments: List[AttachmentMetadata]) -> List[AttachmentFinding]:
        return [self._analyze_one(a) for a in attachments]

    def _analyze_one(self, attachment: AttachmentMetadata) -> AttachmentFinding:
        filename = attachment.filename.lower()
        ext = self._get_extension(filename)
        is_exe = ext in DANGEROUS_EXTENSIONS
        is_double = self._has_double_extension(filename)
        is_suspicious_type = is_exe or attachment.mime_type in (
            "application/x-executable", "application/x-msdownload",
        )

        threats = []
        if is_exe:
            threats.append("executable_file_type")
        if is_double:
            threats.append("double_extension")
        if is_suspicious_type:
            threats.append("suspicious_mime_type")

        score = min(len(threats) * 0.3 + (0.4 if is_exe else 0.0), 1.0)

        return AttachmentFinding(
            filename=attachment.filename,
            risk_score=round(score, 3),
            is_executable=is_exe,
            is_double_extension=is_double,
            is_suspicious_type=is_suspicious_type,
            threats=threats,
        )

    def _get_extension(self, filename: str) -> str:
        parts = filename.rsplit(".", 1)
        return f".{parts[-1]}" if len(parts) > 1 else ""

    def _has_double_extension(self, filename: str) -> bool:
        # e.g. "invoice.pdf.exe"
        parts = filename.split(".")
        if len(parts) >= 3:
            penultimate_ext = f".{parts[-2]}"
            return penultimate_ext in {".pdf", ".doc", ".xls", ".jpg", ".png", ".txt"}
        return False
