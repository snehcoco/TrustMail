"""
Header Analyzer Service
========================
Parses and scores email authentication headers:
  - SPF (Sender Policy Framework)
  - DKIM (DomainKeys Identified Mail)
  - DMARC (Domain-based Message Authentication)
  - Reply-To / Return-Path mismatches
  - Received chain anomalies
  - Forged / suspicious headers
"""

from __future__ import annotations

import re
from typing import List, Optional, Tuple

from api.schemas.request_schemas import HeaderAnalyzeRequest
from api.schemas.response_schemas import (
    HeaderAnalyzeResponse,
    HeaderFinding,
    RiskLevel,
)


class HeaderAnalyzer:
    """Stateless email header analyzer."""

    async def analyze(self, request: HeaderAnalyzeRequest) -> HeaderAnalyzeResponse:
        findings: List[HeaderFinding] = []
        total_score = 0

        h = request.headers

        # ── SPF ───────────────────────────────────────────────────────────────
        spf_pass, spf_finding = self._check_spf(h.spf, h.authentication_results)
        findings.append(spf_finding)
        total_score += spf_finding.score_contribution

        # ── DKIM ──────────────────────────────────────────────────────────────
        dkim_pass, dkim_finding = self._check_dkim(h.dkim, h.authentication_results)
        findings.append(dkim_finding)
        total_score += dkim_finding.score_contribution

        # ── DMARC ─────────────────────────────────────────────────────────────
        dmarc_pass, dmarc_finding = self._check_dmarc(h.dmarc, h.authentication_results)
        findings.append(dmarc_finding)
        total_score += dmarc_finding.score_contribution

        # ── Reply-To mismatch ─────────────────────────────────────────────────
        reply_mismatch = False
        if h.from_ and h.reply_to:
            reply_mismatch, rt_finding = self._check_reply_to(h.from_, h.reply_to)
            findings.append(rt_finding)
            total_score += rt_finding.score_contribution

        # ── Return-Path mismatch ──────────────────────────────────────────────
        if h.from_ and h.return_path:
            _, rp_finding = self._check_return_path(h.from_, h.return_path)
            findings.append(rp_finding)
            total_score += rp_finding.score_contribution

        # ── Received chain ────────────────────────────────────────────────────
        if h.received:
            chain_findings = self._check_received_chain(h.received)
            findings.extend(chain_findings)
            total_score += sum(f.score_contribution for f in chain_findings)

        # ── X-Originating-IP ─────────────────────────────────────────────────
        if h.x_originating_ip:
            ip_finding = self._check_originating_ip(h.x_originating_ip)
            if ip_finding:
                findings.append(ip_finding)
                total_score += ip_finding.score_contribution

        # Normalize to [0, 1]
        risk_score = min(total_score / 100.0, 1.0)
        risk_level = self._score_to_level(risk_score)

        summary = self._build_summary(findings, spf_pass, dkim_pass, dmarc_pass)

        return HeaderAnalyzeResponse(
            risk_score=round(risk_score, 4),
            risk_level=risk_level,
            findings=findings,
            spf_pass=spf_pass,
            dkim_pass=dkim_pass,
            dmarc_pass=dmarc_pass,
            reply_to_mismatch=reply_mismatch,
            summary=summary,
        )

    # ── Individual checks ─────────────────────────────────────────────────────

    def _check_spf(self, spf_header: Optional[str], auth_results: Optional[str]) -> Tuple[Optional[bool], HeaderFinding]:
        """Checks SPF status from dedicated header or Authentication-Results."""
        result_str = spf_header or ""
        if auth_results:
            if "spf=pass" in auth_results.lower():
                result_str = "pass"
            elif "spf=fail" in auth_results.lower():
                result_str = "fail"
            elif "spf=softfail" in auth_results.lower():
                result_str = "softfail"

        if not result_str:
            return None, HeaderFinding(
                check="SPF", result="Missing", severity="high",
                detail="No SPF record found in headers",
                score_contribution=20,
            )
        if "fail" in result_str.lower():
            return False, HeaderFinding(
                check="SPF", result="Fail", severity="critical",
                detail=f"SPF authentication failed: {result_str}",
                score_contribution=25,
            )
        if "softfail" in result_str.lower():
            return False, HeaderFinding(
                check="SPF", result="Softfail", severity="high",
                detail="SPF softfail — sender not fully authorized",
                score_contribution=15,
            )
        return True, HeaderFinding(
            check="SPF", result="Pass", severity="info",
            detail="SPF authentication passed",
            score_contribution=0,
        )

    def _check_dkim(self, dkim_header: Optional[str], auth_results: Optional[str]) -> Tuple[Optional[bool], HeaderFinding]:
        result_str = dkim_header or ""
        if auth_results:
            if "dkim=pass" in auth_results.lower():
                result_str = "pass"
            elif "dkim=fail" in auth_results.lower():
                result_str = "fail"

        if not result_str:
            return None, HeaderFinding(
                check="DKIM", result="Missing", severity="high",
                detail="No DKIM signature found",
                score_contribution=20,
            )
        if "fail" in result_str.lower():
            return False, HeaderFinding(
                check="DKIM", result="Fail", severity="critical",
                detail="DKIM signature verification failed — possible tampering",
                score_contribution=25,
            )
        return True, HeaderFinding(
            check="DKIM", result="Pass", severity="info",
            detail="DKIM signature valid",
            score_contribution=0,
        )

    def _check_dmarc(self, dmarc_header: Optional[str], auth_results: Optional[str]) -> Tuple[Optional[bool], HeaderFinding]:
        result_str = dmarc_header or ""
        if auth_results and "dmarc=" in auth_results.lower():
            if "dmarc=pass" in auth_results.lower():
                result_str = "pass"
            elif "dmarc=fail" in auth_results.lower():
                result_str = "fail"

        if not result_str:
            return None, HeaderFinding(
                check="DMARC", result="Missing", severity="medium",
                detail="No DMARC policy enforced",
                score_contribution=15,
            )
        if "fail" in result_str.lower():
            return False, HeaderFinding(
                check="DMARC", result="Fail", severity="critical",
                detail="DMARC policy check failed",
                score_contribution=20,
            )
        return True, HeaderFinding(
            check="DMARC", result="Pass", severity="info",
            detail="DMARC policy satisfied",
            score_contribution=0,
        )

    def _check_reply_to(self, from_: str, reply_to: str) -> Tuple[bool, HeaderFinding]:
        from_domain = self._extract_domain(from_)
        rt_domain = self._extract_domain(reply_to)
        if from_domain and rt_domain and from_domain.lower() != rt_domain.lower():
            return True, HeaderFinding(
                check="Reply-To Mismatch", result="Suspicious", severity="high",
                detail=f"From domain ({from_domain}) ≠ Reply-To domain ({rt_domain})",
                score_contribution=15,
            )
        return False, HeaderFinding(
            check="Reply-To", result="Pass", severity="info",
            detail="Reply-To matches sender domain",
            score_contribution=0,
        )

    def _check_return_path(self, from_: str, return_path: str) -> Tuple[bool, HeaderFinding]:
        from_domain = self._extract_domain(from_)
        rp_domain = self._extract_domain(return_path)
        if from_domain and rp_domain and from_domain.lower() != rp_domain.lower():
            return True, HeaderFinding(
                check="Return-Path Mismatch", result="Suspicious", severity="medium",
                detail=f"From domain ({from_domain}) ≠ Return-Path ({rp_domain})",
                score_contribution=10,
            )
        return False, HeaderFinding(
            check="Return-Path", result="Pass", severity="info",
            detail="Return-Path matches sender domain",
            score_contribution=0,
        )

    def _check_received_chain(self, received: list) -> List[HeaderFinding]:
        """Detect anomalies in the Received header chain."""
        findings = []
        if len(received) > 10:
            findings.append(HeaderFinding(
                check="Received Chain", result="Suspicious", severity="medium",
                detail=f"Unusually long received chain ({len(received)} hops)",
                score_contribution=10,
            ))
        return findings

    def _check_originating_ip(self, ip_header: str) -> Optional[HeaderFinding]:
        # Flag if IP is in private ranges (internal spoofing)
        private_ranges = ["10.", "192.168.", "172.16.", "127."]
        if any(ip_header.startswith(p) for p in private_ranges):
            return HeaderFinding(
                check="X-Originating-IP", result="Suspicious", severity="medium",
                detail=f"Email claims to originate from private IP: {ip_header}",
                score_contribution=10,
            )
        return None

    def _extract_domain(self, email: str) -> Optional[str]:
        match = re.search(r"@([\w.\-]+)", email)
        return match.group(1) if match else None

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

    def _build_summary(self, findings, spf_pass, dkim_pass, dmarc_pass) -> str:
        fail_count = sum(1 for f in findings if f.result in ("Fail", "Missing", "Suspicious"))
        if fail_count == 0:
            return "All authentication checks passed."
        return f"{fail_count} authentication issue(s) detected. SPF={'✓' if spf_pass else '✗'}, DKIM={'✓' if dkim_pass else '✗'}, DMARC={'✓' if dmarc_pass else '✗'}"
