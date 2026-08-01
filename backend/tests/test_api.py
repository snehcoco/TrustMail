"""
API Integration Tests
=====================
Tests all REST endpoints using FastAPI TestClient.
Does not require real models to be loaded — uses mock model loader.
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch
import numpy as np


# ── Test fixtures ──────────────────────────────────────────────────────────────

@pytest.fixture
def mock_model_loader():
    """Create a mock model loader that returns realistic dummy predictions."""
    loader = MagicMock()
    loader.is_ready.return_value = True
    loader.get_model_version.return_value = "1.0.0-test"
    loader.get_loaded_models.return_value = {
        "distilbert_onnx": False,
        "random_forest": True,
        "xgboost": True,
        "lightgbm": False,
        "catboost": False,
        "logistic_regression": True,
    }
    loader.get_model_versions.return_value = {"random_forest": "1.0.0"}

    # Mock classical models to return fixed predictions
    mock_clf = MagicMock()
    mock_clf.predict_proba.return_value = np.array([[0.3, 0.7]])
    loader.get_classical_model.return_value = mock_clf
    loader.get_onnx_runner.side_effect = RuntimeError("ONNX not loaded in tests")

    return loader


@pytest.fixture
def client(mock_model_loader):
    """Create test client with mocked model loader."""
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    from api.app import create_app
    app = create_app()
    app.state.model_loader = mock_model_loader

    with TestClient(app) as c:
        yield c


# ── Health endpoints ───────────────────────────────────────────────────────────

class TestHealthEndpoints:
    def test_health_check(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "version" in data
        assert "uptime_seconds" in data

    def test_version_endpoint(self, client):
        response = client.get("/version")
        assert response.status_code == 200
        data = response.json()
        assert "api_version" in data
        assert "model_version" in data
        assert "python_version" in data

    def test_metrics_endpoint(self, client):
        response = client.get("/metrics")
        assert response.status_code == 200
        data = response.json()
        assert "total_requests" in data
        assert "avg_latency_ms" in data

    def test_status_endpoint(self, client):
        response = client.get("/status")
        assert response.status_code == 200
        data = response.json()
        assert "models_loaded" in data
        assert "memory_usage_mb" in data


# ── Analyze endpoint ───────────────────────────────────────────────────────────

class TestAnalyzeEndpoint:
    PHISHING_PAYLOAD = {
        "subject": "URGENT: Your account has been suspended!",
        "body_text": "Click here immediately to verify your password: http://192.168.1.1/verify",
        "sender": "security@micr0soft.tk",
        "reply_to": "hacker@evil.xyz",
        "urls": ["http://192.168.1.1/verify", "http://paypa1.com/secure"],
        "include_explanation": False,
    }

    SAFE_PAYLOAD = {
        "subject": "Q4 Report",
        "body_text": "Hi team, please find the Q4 financial report attached.",
        "sender": "reports@company.com",
        "include_explanation": False,
    }

    def test_analyze_phishing_email(self, client):
        response = client.post("/api/v1/analyze", json=self.PHISHING_PAYLOAD)
        assert response.status_code == 200
        data = response.json()
        assert "risk_level" in data
        assert "risk_score" in data
        assert "confidence" in data
        assert 0.0 <= data["risk_score"] <= 1.0
        assert 0.0 <= data["confidence"] <= 1.0

    def test_analyze_safe_email(self, client):
        response = client.post("/api/v1/analyze", json=self.SAFE_PAYLOAD)
        assert response.status_code == 200
        data = response.json()
        assert data["risk_level"] in ["safe", "low_risk", "suspicious", "phishing", "highly_dangerous"]

    def test_analyze_requires_at_least_one_field(self, client):
        response = client.post("/api/v1/analyze", json={})
        assert response.status_code == 422  # Validation error

    def test_analyze_response_has_url_findings(self, client):
        response = client.post("/api/v1/analyze", json=self.PHISHING_PAYLOAD)
        assert response.status_code == 200
        data = response.json()
        # IP-based URL should be detected
        url_findings = data.get("url_findings", [])
        assert len(url_findings) > 0

    def test_analyze_detects_reply_to_mismatch(self, client):
        response = client.post("/api/v1/analyze", json=self.PHISHING_PAYLOAD)
        assert response.status_code == 200
        data = response.json()
        assert data.get("reply_to_mismatch") is True

    def test_analyze_subject_only(self, client):
        response = client.post("/api/v1/analyze", json={"subject": "Test email"})
        assert response.status_code == 200


# ── Batch endpoint ─────────────────────────────────────────────────────────────

class TestBatchEndpoint:
    def test_batch_multiple_emails(self, client):
        payload = {
            "emails": [
                {"subject": "Test 1", "body_text": "Safe email content"},
                {"subject": "URGENT", "body_text": "Click here to verify your account!"},
            ],
            "include_explanation": False,
        }
        response = client.post("/api/v1/batch", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["total_analyzed"] == 2
        assert len(data["results"]) == 2

    def test_batch_rejects_empty(self, client):
        payload = {"emails": []}
        response = client.post("/api/v1/batch", json=payload)
        assert response.status_code == 422


# ── URL endpoint ───────────────────────────────────────────────────────────────

class TestURLEndpoint:
    def test_analyze_suspicious_urls(self, client):
        payload = {
            "urls": [
                "http://192.168.1.1/verify",
                "http://paypa1.com/secure-login",
                "https://bit.ly/3xZk9q",
            ]
        }
        response = client.post("/api/v1/urls", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["urls_analyzed"] == 3
        assert len(data["findings"]) == 3
        # IP-based URL should have high risk
        ip_finding = next((f for f in data["findings"] if "192.168" in f["url"]), None)
        assert ip_finding is not None
        assert ip_finding["is_ip_based"] is True

    def test_url_typosquatting_detection(self, client):
        payload = {"urls": ["http://paypa1.com/login"]}
        response = client.post("/api/v1/urls", json=payload)
        assert response.status_code == 200
        data = response.json()
        finding = data["findings"][0]
        assert finding["is_typosquatting"] is True


# ── Header endpoint ────────────────────────────────────────────────────────────

class TestHeaderEndpoint:
    def test_failing_spf_dkim(self, client):
        payload = {
            "headers": {
                "from": "ceo@company.com",
                "reply_to": "attacker@evil.com",
                "spf": "fail",
                "dkim": "fail",
                "authentication_results": "spf=fail dkim=fail dmarc=fail",
            }
        }
        response = client.post("/api/v1/headers", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["spf_pass"] is False
        assert data["dkim_pass"] is False
        assert data["reply_to_mismatch"] is True
        assert data["risk_score"] > 0.5


# ── Attachment endpoint ────────────────────────────────────────────────────────

class TestAttachmentEndpoint:
    def test_executable_attachment(self, client):
        payload = {
            "attachments": [
                {"filename": "invoice.pdf.exe", "mime_type": "application/x-executable"},
                {"filename": "report.pdf", "mime_type": "application/pdf"},
            ]
        }
        response = client.post("/api/v1/attachments", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["attachments_analyzed"] == 2
        exe_finding = next(
            (f for f in data["findings"] if "exe" in f["filename"].lower()), None
        )
        assert exe_finding is not None
        assert exe_finding["is_executable"] is True
        assert exe_finding["is_double_extension"] is True
