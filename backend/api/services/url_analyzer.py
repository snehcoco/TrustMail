"""
URL Analyzer Service
=====================
Analyzes URLs for a comprehensive set of phishing indicators:
  - Homograph / IDN attacks
  - Typosquatting (lexical similarity to trusted brands)
  - Shortened URLs (bit.ly, tinyurl, etc.)
  - IP-based URLs
  - Suspicious TLDs
  - URL encoding / obfuscation
  - Excessive query parameters
  - Redirect chain depth
"""

from __future__ import annotations

import re
import urllib.parse
from difflib import SequenceMatcher
from typing import List, Tuple

from loguru import logger

from api.schemas.request_schemas import URLAnalyzeRequest
from api.schemas.response_schemas import URLAnalyzeResponse, URLFinding

# ── Reference sets ────────────────────────────────────────────────────────────

TRUSTED_BRANDS = [
    "google", "microsoft", "apple", "amazon", "paypal", "netflix",
    "facebook", "instagram", "twitter", "linkedin", "dropbox",
    "chase", "wellsfargo", "bankofamerica", "citibank", "irs",
    "dhl", "fedex", "ups", "usps",
]

URL_SHORTENERS = {
    "bit.ly", "tinyurl.com", "t.co", "goo.gl", "ow.ly", "buff.ly",
    "shorturl.at", "rb.gy", "cutt.ly", "is.gd", "v.gd", "tiny.cc",
    "su.pr", "youtu.be", "adf.ly", "bit.do", "mcaf.ee",
}

SUSPICIOUS_TLDS = {
    ".xyz", ".top", ".click", ".loan", ".work", ".men", ".gq",
    ".tk", ".ml", ".cf", ".ga", ".pw", ".cc", ".su", ".bid",
    ".win", ".download", ".racing", ".review", ".science",
}

# Homograph character map (IDN spoofing via Unicode lookalikes)
HOMOGRAPH_MAP = {
    "а": "a", "е": "e", "о": "o", "р": "p", "с": "c",  # Cyrillic → Latin
    "ı": "i", "ρ": "p", "ν": "v", "μ": "u",             # Greek → Latin
}

IP_PATTERN = re.compile(
    r"https?://(\d{1,3}\.){3}\d{1,3}"
)
EXCESSIVE_PARAMS_THRESHOLD = 5
TYPOSQUAT_THRESHOLD = 0.80   # Similarity ratio above which we flag


class URLAnalyzer:
    """Stateless URL threat analyzer."""

    async def analyze(self, request: URLAnalyzeRequest) -> URLAnalyzeResponse:
        findings = [self._analyze_single(url) for url in request.urls]
        overall = max((f.risk_score for f in findings), default=0.0)
        high_risk = sum(1 for f in findings if f.risk_score >= 0.65)

        return URLAnalyzeResponse(
            urls_analyzed=len(findings),
            high_risk_urls=high_risk,
            findings=findings,
            overall_risk_score=round(overall, 4),
        )

    def _analyze_single(self, raw_url: str) -> URLFinding:
        threats: List[str] = []
        score = 0.0

        # Decode percent-encoding before analysis
        try:
            decoded = urllib.parse.unquote(raw_url)
        except Exception:
            decoded = raw_url

        # Normalize
        url = decoded.strip()
        try:
            parsed = urllib.parse.urlparse(url if "://" in url else f"https://{url}")
        except Exception:
            return URLFinding(url=raw_url, risk_score=0.5, threats=["unparseable_url"])

        hostname = parsed.hostname or ""
        path = parsed.path or ""
        query = parsed.query or ""

        # ── 1. IP-based URL ──────────────────────────────────────────────────
        is_ip = bool(IP_PATTERN.match(url))
        if is_ip:
            threats.append("ip_based_url")
            score += 0.20

        # ── 2. Shortened URL ─────────────────────────────────────────────────
        is_shortened = hostname in URL_SHORTENERS
        if is_shortened:
            threats.append("shortened_url")
            score += 0.15

        # ── 3. Suspicious TLD ────────────────────────────────────────────────
        tld = self._get_tld(hostname)
        suspicious_tld = tld in SUSPICIOUS_TLDS
        if suspicious_tld:
            threats.append("suspicious_tld")
            score += 0.10

        # ── 4. Homograph / IDN attack ────────────────────────────────────────
        is_homograph = self._detect_homograph(hostname)
        if is_homograph:
            threats.append("homograph_attack")
            score += 0.30

        # ── 5. Typosquatting ─────────────────────────────────────────────────
        is_typosquat, matched_brand = self._detect_typosquat(hostname)
        if is_typosquat and matched_brand:
            threats.append(f"typosquatting_mimics_{matched_brand}")
            score += 0.25

        # ── 6. Encoded URL ───────────────────────────────────────────────────
        if "%" in raw_url and not is_homograph:
            threats.append("encoded_url")
            score += 0.10

        # ── 7. Excessive query parameters ────────────────────────────────────
        params = urllib.parse.parse_qs(query)
        if len(params) > EXCESSIVE_PARAMS_THRESHOLD:
            threats.append("excessive_query_params")
            score += 0.05

        # ── 8. Deceptive HTTPS (HTTPS but still malicious indicators) ────────
        if parsed.scheme == "https" and (is_homograph or is_typosquat):
            threats.append("deceptive_https")
            score += 0.10

        # ── 9. Suspicious subdomain depth ────────────────────────────────────
        subdomains = hostname.split(".")
        if len(subdomains) > 4:
            threats.append("excessive_subdomain_depth")
            score += 0.10

        # ── 10. Data URI / javascript scheme ─────────────────────────────────
        if raw_url.startswith(("data:", "javascript:", "vbscript:")):
            threats.append("dangerous_uri_scheme")
            score += 0.40

        return URLFinding(
            url=raw_url,
            risk_score=min(round(score, 4), 1.0),
            threats=threats,
            is_shortened=is_shortened,
            is_ip_based=is_ip,
            is_homograph=is_homograph,
            is_typosquatting=is_typosquat,
            suspicious_tld=suspicious_tld,
            redirect_depth=0,  # Would require live resolution
            decoded_url=decoded if decoded != raw_url else None,
        )

    def _get_tld(self, hostname: str) -> str:
        parts = hostname.split(".")
        return f".{parts[-1]}" if parts else ""

    def _detect_homograph(self, hostname: str) -> bool:
        """Detect Punycode or Unicode homograph attacks."""
        if hostname.startswith("xn--"):
            return True
        normalized = "".join(HOMOGRAPH_MAP.get(c, c) for c in hostname)
        return normalized != hostname

    def _detect_typosquat(self, hostname: str) -> Tuple[bool, str]:
        """
        Compare hostname against trusted brands using SequenceMatcher.
        Returns (is_typosquat, matched_brand_name).
        """
        # Strip TLD for comparison
        base = hostname.rsplit(".", 1)[0] if "." in hostname else hostname
        # Remove common prefixes like www, secure, login
        base = re.sub(r"^(www|secure|login|account|signin|verify)\.", "", base)

        for brand in TRUSTED_BRANDS:
            ratio = SequenceMatcher(None, base.lower(), brand).ratio()
            if TYPOSQUAT_THRESHOLD <= ratio < 1.0:
                return True, brand
        return False, ""
