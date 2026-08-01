# TrustMail — API Reference

Base URL: `http://127.0.0.1:8000`

Interactive docs: `http://127.0.0.1:8000/docs`

---

## `GET /health`

Returns backend operational status.

### Response
```json
{
  "status": "ok",
  "version": "1.0.0",
  "models_loaded": true,
  "mode": "full_ai",
  "uptime_seconds": 3600,
  "total_analyzed": 142,
  "phishing_detected": 23,
  "avg_latency_ms": 847
}
```

| Field | Type | Description |
|---|---|---|
| `status` | `"ok" \| "degraded"` | Overall health |
| `models_loaded` | bool | True if ML models are loaded |
| `mode` | `"full_ai" \| "heuristic"` | Current analysis mode |
| `uptime_seconds` | int | Seconds since server start |
| `total_analyzed` | int | Total emails analyzed this session |

---

## `GET /status`

Detailed status with per-model state and system info.

### Response
```json
{
  "status": "ok",
  "models": {
    "classical_ensemble": "loaded",
    "onnx_transformer": "loaded",
    "meta_learner": "loaded",
    "feature_extractor": "loaded"
  },
  "system": {
    "cpu_percent": 12.3,
    "memory_mb": 842
  }
}
```

---

## `POST /api/v1/analyze`

Full email threat analysis. Primary endpoint used by the Chrome extension.

### Request Body

```json
{
  "subject": "Urgent: Your account has been compromised",
  "body_text": "Dear customer, your account...",
  "body_html": "<html>...</html>",
  "sender": "security@paypa1.com",
  "sender_domain": "paypa1.com",
  "reply_to": "collect@evil.ru",
  "urls": [
    "http://paypa1.com/verify?token=abc123",
    "https://bit.ly/3xPhish"
  ],
  "platform": "gmail",
  "email_id": "msg-1234567890",
  "include_explanation": true
}
```

| Field | Type | Required | Max Length | Description |
|---|---|---|---|---|
| `subject` | string | ✅ | 2,000 | Email subject line |
| `body_text` | string | ❌ | 50,000 | Plain text body |
| `body_html` | string | ❌ | 200,000 | HTML body |
| `sender` | string | ❌ | 500 | From address |
| `sender_domain` | string | ❌ | 255 | Domain extracted from sender |
| `reply_to` | string | ❌ | 500 | Reply-To header value |
| `urls` | string[] | ❌ | 200 items | URLs extracted from body |
| `platform` | string | ❌ | 50 | `gmail`, `outlook`, `yahoo`, `protonmail` |
| `email_id` | string | ❌ | 100 | Unique identifier for caching |
| `include_explanation` | bool | ❌ | — | Include SHAP + LIME (slower) |

> **Inbox scan mode:** Set `body_text` and `body_html` to empty string `""`. The pipeline will use header-only features, which is ~10x faster.

### Response

```json
{
  "email_id": "msg-1234567890",
  "risk_level": "phishing",
  "risk_score": 0.847,
  "confidence": 0.931,
  "scan_duration_ms": 1243,
  "analysis_timestamp": "2024-01-15T10:23:41Z",
  "model_version": "1.0.0",
  "mode": "full_ai",

  "model_predictions": [
    { "model_name": "RandomForest", "phishing_probability": 0.82 },
    { "model_name": "XGBoost", "phishing_probability": 0.89 },
    { "model_name": "LightGBM", "phishing_probability": 0.84 },
    { "model_name": "DistilBERT", "phishing_probability": 0.91 }
  ],

  "threat_categories": ["credential_harvesting", "domain_spoofing", "urgency_manipulation"],

  "top_reasons": [
    "Sender domain (paypa1.com) is a homograph of paypal.com",
    "Reply-To address is in a different domain (evil.ru)",
    "Urgent language requesting account verification",
    "2 shortened URLs detected"
  ],

  "suspicious_keywords": ["verify", "suspended", "urgent", "immediately", "account"],

  "header_findings": [
    { "check": "SPF", "result": "Fail", "detail": "SPF record not found for paypa1.com" },
    { "check": "DKIM", "result": "Missing", "detail": "No DKIM signature present" },
    { "check": "DMARC", "result": "Fail", "detail": "No DMARC policy for paypa1.com" },
    { "check": "Reply-To Mismatch", "result": "Suspicious", "detail": "Reply-To domain differs from sender" }
  ],

  "url_findings": [
    {
      "url": "http://paypa1.com/verify?token=abc123",
      "risk_score": 0.91,
      "is_homograph": true,
      "is_ip_based": false,
      "is_shortened": false,
      "is_typosquatting": true,
      "suspicious_tld": false,
      "threat_indicators": ["homograph_domain", "typosquatting"]
    },
    {
      "url": "https://bit.ly/3xPhish",
      "risk_score": 0.65,
      "is_shortened": true,
      "threat_indicators": ["url_shortener"]
    }
  ],

  "shap_explanation": {
    "top_features": [
      { "feature": "reply_to_mismatch", "importance": 0.312, "direction": "phishing" },
      { "feature": "spf_result", "importance": 0.287, "direction": "phishing" },
      { "feature": "homograph_score", "importance": 0.241, "direction": "phishing" },
      { "feature": "urgent_keyword_count", "importance": 0.198, "direction": "phishing" },
      { "feature": "dkim_result", "importance": -0.145, "direction": "safe" }
    ]
  }
}
```

### Error Responses

| Status | Body | Cause |
|---|---|---|
| `422` | `{"detail": [{"loc": [...], "msg": "..."}]}` | Invalid request fields |
| `500` | `{"error": "Analysis failed", "detail": "..."}` | Pipeline error |

---

## `POST /api/v1/batch`

Analyze up to 50 emails in a single request.

### Request
```json
{
  "emails": [
    { "subject": "...", "sender": "...", "email_id": "e1" },
    { "subject": "...", "sender": "...", "email_id": "e2" }
  ],
  "include_explanation": false
}
```

### Response
```json
{
  "results": [
    { "email_id": "e1", "risk_level": "safe", "risk_score": 0.12, ... },
    { "email_id": "e2", "risk_level": "phishing", "risk_score": 0.84, ... }
  ],
  "total_analyzed": 2,
  "duration_ms": 2100
}
```

---

## `POST /api/v1/headers`

Header-only analysis (no ML). Fast SPF/DKIM/DMARC checking.

### Request
```json
{
  "sender": "noreply@paypa1.com",
  "reply_to": "collect@evil.ru",
  "raw_headers": "Received: from ...\nMessage-ID: ...",
  "email_id": "msg-abc"
}
```

### Response
```json
{
  "header_findings": [
    { "check": "SPF", "result": "Fail", "detail": "..." },
    { "check": "Reply-To Mismatch", "result": "Suspicious", "detail": "..." }
  ],
  "header_risk_score": 0.72
}
```

---

## `POST /api/v1/urls`

URL risk scoring only. No email body analysis.

### Request
```json
{
  "urls": ["https://paypa1.com/login", "http://bit.ly/3abc"],
  "email_id": "msg-xyz"
}
```

### Response
```json
{
  "url_findings": [
    { "url": "...", "risk_score": 0.91, "is_homograph": true, ... }
  ]
}
```

---

## `POST /api/v1/explain`

Re-generate SHAP/LIME explanations for a previously-analyzed email.

### Request
```json
{
  "subject": "...",
  "body_text": "...",
  "email_id": "msg-abc"
}
```

### Response
```json
{
  "shap_explanation": { "top_features": [...] },
  "lime_explanation": { "word_contributions": [...] },
  "top_reasons": [...]
}
```

---

## Common Field Reference

### `risk_level` values
| Value | Meaning |
|---|---|
| `"safe"` | No significant threat indicators |
| `"low_risk"` | Minor concerns; proceed carefully |
| `"suspicious"` | Multiple indicators; verify sender |
| `"phishing"` | High-confidence phishing attempt |
| `"highly_dangerous"` | Critical threat; delete immediately |

### `header_findings[].result` values
| Value | Meaning |
|---|---|
| `"Pass"` | Authentication check passed |
| `"Fail"` | Authentication check failed (high risk) |
| `"Softfail"` | Partial authentication failure |
| `"Missing"` | Header absent (suspicious) |
| `"Suspicious"` | Anomalous value detected |
