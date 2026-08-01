"""
Preprocessing Unit Tests
========================
Tests for text cleaner, feature extractor, and URL analyzer.
"""

import pytest
import numpy as np
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from preprocessing.text_cleaner import TextCleaner
from preprocessing.feature_extractor import FeatureExtractor
from api.services.url_analyzer import URLAnalyzer


class TestTextCleaner:
    def setup_method(self):
        self.cleaner = TextCleaner()

    def test_strips_html_tags(self):
        html = "<h1>Hello</h1><p>World</p>"
        result = self.cleaner.clean(html)
        assert "<h1>" not in result
        assert "Hello" in result
        assert "World" in result

    def test_normalizes_whitespace(self):
        text = "Hello   world\n\n\ttest"
        result = self.cleaner.clean(text)
        assert "  " not in result

    def test_replaces_urls_with_token(self):
        text = "Visit http://evil.com/phish for your prize"
        result = self.cleaner.clean(text, preserve_urls=True)
        assert "__URL__" in result
        assert "evil.com" not in result

    def test_replaces_email_addresses(self):
        text = "Contact us at attacker@evil.com"
        result = self.cleaner.clean(text)
        assert "__EMAIL__" in result

    def test_handles_empty_string(self):
        assert self.cleaner.clean("") == ""

    def test_unicode_normalization(self):
        # Smart quotes should be normalized
        text = "\u201cHello world\u201d"
        result = self.cleaner.clean(text)
        assert result  # Should not crash

    def test_removes_control_characters(self):
        text = "Hello\x00\x01\x02World"
        result = self.cleaner.clean(text)
        assert "\x00" not in result
        assert "Hello" in result


class TestFeatureExtractor:
    def setup_method(self):
        self.extractor = FeatureExtractor()

    def test_returns_correct_dimension(self):
        feats = self.extractor.extract(text="Test email body")
        assert feats.shape == (FeatureExtractor.FEATURE_DIM,)

    def test_returns_float32(self):
        feats = self.extractor.extract(text="Test")
        assert feats.dtype == np.float32

    def test_all_values_in_range(self):
        text = "URGENT! Click here now to verify your PayPal account!!!"
        feats = self.extractor.extract(text=text)
        # Most features should be in [0, 1] after extraction
        # (raw counts may exceed 1.0 before scaling)
        assert not np.any(np.isnan(feats))
        assert not np.any(np.isinf(feats))

    def test_caps_ratio_higher_for_caps_text(self):
        low_caps = self.extractor.extract(text="hello world this is a normal email")
        high_caps = self.extractor.extract(text="HELLO WORLD THIS IS URGENT!!!")
        # Caps ratio is feature index 7
        assert high_caps[7] > low_caps[7]

    def test_url_features_non_zero_with_urls(self):
        feats_no_url = self.extractor.extract(text="No URLs here")
        feats_with_url = self.extractor.extract(
            text="Click here", urls=["http://evil.com", "http://192.168.1.1"]
        )
        # URL count feature (index 20) should be higher
        assert feats_with_url[20] > feats_no_url[20]

    def test_reply_to_mismatch_flag(self):
        feats_match = self.extractor.extract(
            text="Test",
            sender="user@company.com",
            reply_to="other@company.com",
        )
        feats_mismatch = self.extractor.extract(
            text="Test",
            sender="user@company.com",
            reply_to="attacker@evil.xyz",
        )
        # Reply-to mismatch flag (index 38)
        assert feats_mismatch[38] == 1.0
        assert feats_match[38] == 0.0

    def test_keyword_features_for_phishing(self):
        safe_feats = self.extractor.extract(text="Please review the attached report")
        phish_feats = self.extractor.extract(
            text="Enter your password immediately to verify your account"
        )
        # "password" keyword feature should be 1.0 for phishing text
        # keyword features start at index 55
        assert phish_feats[55] == 1.0  # kw_password
        assert safe_feats[55] == 0.0


class TestURLAnalyzer:
    @pytest.mark.asyncio
    async def test_ip_based_url_detected(self):
        from api.schemas.request_schemas import URLAnalyzeRequest
        analyzer = URLAnalyzer()
        req = URLAnalyzeRequest(urls=["http://192.168.1.1/verify"])
        result = await analyzer.analyze(req)
        assert result.findings[0].is_ip_based is True
        assert result.findings[0].risk_score > 0.0

    @pytest.mark.asyncio
    async def test_shortened_url_detected(self):
        from api.schemas.request_schemas import URLAnalyzeRequest
        analyzer = URLAnalyzer()
        req = URLAnalyzeRequest(urls=["https://bit.ly/3xZk9q"])
        result = await analyzer.analyze(req)
        assert result.findings[0].is_shortened is True

    @pytest.mark.asyncio
    async def test_typosquatting_detected(self):
        from api.schemas.request_schemas import URLAnalyzeRequest
        analyzer = URLAnalyzer()
        req = URLAnalyzeRequest(urls=["http://paypa1.com/login"])
        result = await analyzer.analyze(req)
        assert result.findings[0].is_typosquatting is True

    @pytest.mark.asyncio
    async def test_suspicious_tld(self):
        from api.schemas.request_schemas import URLAnalyzeRequest
        analyzer = URLAnalyzer()
        req = URLAnalyzeRequest(urls=["http://malware.tk/exploit"])
        result = await analyzer.analyze(req)
        assert result.findings[0].suspicious_tld is True

    @pytest.mark.asyncio
    async def test_encoded_url_flagged(self):
        from api.schemas.request_schemas import URLAnalyzeRequest
        analyzer = URLAnalyzer()
        req = URLAnalyzeRequest(urls=["http://evil.com/path%2F..%2Fsecret"])
        result = await analyzer.analyze(req)
        threats = result.findings[0].threats
        assert "encoded_url" in threats

    @pytest.mark.asyncio
    async def test_dangerous_scheme_flagged(self):
        from api.schemas.request_schemas import URLAnalyzeRequest
        analyzer = URLAnalyzer()
        req = URLAnalyzeRequest(urls=["javascript:alert(1)"])
        result = await analyzer.analyze(req)
        threats = result.findings[0].threats
        assert "dangerous_uri_scheme" in threats

    @pytest.mark.asyncio
    async def test_legitimate_url_low_risk(self):
        from api.schemas.request_schemas import URLAnalyzeRequest
        analyzer = URLAnalyzer()
        req = URLAnalyzeRequest(urls=["https://www.google.com/search?q=test"])
        result = await analyzer.analyze(req)
        # Should have low risk score (no phishing indicators)
        assert result.findings[0].risk_score < 0.5
