# TrustMail — Backend Documentation

## Overview

The TrustMail backend is a **FastAPI** application that exposes REST endpoints for email analysis. It loads a **classical ML ensemble** (no deep learning) once on startup and handles requests from the Chrome extension. All inference is CPU-only with no ONNX, PyTorch, or GPU dependency.

---

## Project Structure

```
backend/
├── app.py                        # Uvicorn entry point
├── api/
│   ├── app.py                    # FastAPI factory (create_app)
│   ├── middleware/
│   │   ├── cors_config.py        # CORS (localhost only)
│   │   ├── rate_limiter.py       # Token-bucket rate limiting
│   │   └── audit_logger.py       # Request/response audit trail
│   ├── routes/
│   │   ├── analyze.py            # POST /api/v1/analyze
│   │   ├── batch.py              # POST /api/v1/batch
│   │   ├── headers.py            # POST /api/v1/headers
│   │   ├── urls.py               # POST /api/v1/urls
│   │   ├── attachments.py        # POST /api/v1/attachments
│   │   ├── explain.py            # POST /api/v1/explain
│   │   └── health.py             # GET /health, GET /status
│   ├── schemas/
│   │   ├── request_schemas.py    # Pydantic request models
│   │   └── response_schemas.py   # Pydantic response models
│   ├── services/
│   │   └── email_analyzer.py     # Main orchestration service
│   └── explainability/
│       ├── shap_explainer.py     # SHAP values
│       └── lime_explainer.py     # LIME explanations
├── config/
│   ├── settings.py               # Pydantic Settings (env-driven)
│   └── model_config.yaml         # Model paths and thresholds
├── inference/
│   ├── model_loader.py           # Loads/caches all models
│   └── ensemble.py               # Ensemble Service | Weighted average of 5 classical models |
| Model Loader | `inference/model_loader.py` | Loads/caches classical models on startup |
├── preprocessing/
│   └── feature_extractor.py      # Text + header + URL feature pipeline
├── training/
│   └── run_training.py           # Self-contained training script (generates data + trains)
```

---

## Application Factory

**File:** `api/app.py` → `create_app()`

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    loader = ModelLoader(settings)
    app.state.model_loader = loader
    loader.load_all()          # Classical models pre-loaded once at startup
    mode = "full AI" if loader.has_trained_models() else "heuristic fallback"
    logger.info(f"TrustMail ready — mode: {mode}")
    yield
    loader.unload_all()        # Cleanup on shutdown
```

**Middleware stack** (applied outermost-last):
1. `CORSMiddleware` — localhost-only origins
2. `GZipMiddleware` — compress responses ≥1KB
3. `AuditLogMiddleware` — log all requests/responses
4. `RateLimitMiddleware` — token bucket (configurable, default: off)

---

## Configuration

**File:** `config/settings.py` (Pydantic BaseSettings)

| Setting | Default | Description |
|---|---|---|
| `HOST` | `127.0.0.1` | Server bind address |
| `PORT` | `8000` | Server port |
| `API_PREFIX` | `/api/v1` | Route prefix |
| `CORS_ORIGINS` | `["http://localhost:*"]` | Allowed CORS origins |
| `RATE_LIMIT_ENABLED` | `False` | Enable rate limiting |
| `RATE_LIMIT_REQUESTS` | `60` | Requests per window |
| `RATE_LIMIT_WINDOW` | `60` | Window size (seconds) |
| `MODELS_DIR` | `trained_models` | Directory containing model files |
| `CLASSICAL_MODEL_FILE` | `ensemble_classical.pkl` | Classical ensemble bundle |
| `HEURISTIC_FALLBACK` | `True` | Use rule scoring when models missing |
| `LOG_LEVEL` | `INFO` | Loguru log level |

Override via environment variables:
```bash
TRUSTMAIL_PORT=9000 python app.py
```

---

## API Routes

### `GET /health`
Returns backend health, model status, version, and metrics.

```json
{
  "status": "ok",
  "version": "1.0.0",
  "models_loaded": true,
  "uptime_seconds": 3600,
  "total_analyzed": 142
}
```

### `GET /status`
Detailed status with per-model load state and memory usage.

### `POST /api/v1/analyze`
Full single-email analysis. See [API Reference](api-documentation.md).

### `POST /api/v1/batch`
Analyze up to 50 emails in a single request. Returns array of `AnalyzeResponse`.

### `POST /api/v1/headers`
Header-only analysis (SPF/DKIM/DMARC). Does not run ML models.

### `POST /api/v1/urls`
URL risk scoring only. Returns per-URL risk breakdown.

### `POST /api/v1/attachments`
Attachment metadata risk scoring (filename, type, size).

### `POST /api/v1/explain`
Re-run SHAP/LIME on a previously analyzed email by email_id.

---

## Services Layer

### `EmailAnalyzer` (`api/services/email_analyzer.py`)

Orchestrates the full pipeline:
```python
class EmailAnalyzer:
    async def analyze(self, request: AnalyzeRequest) -> AnalyzeResponse:
        features = self.extractor.extract(request)
        ensemble_score, confidence, predictions = self.ensemble.predict(features, text)
        final_score = combine(ensemble_score, header_score, url_score, nlp_score)
        if not predictions:  # Heuristic mode
            confidence = min(abs(final_score - 0.5) * 2.0, 0.75)
        explanation = self.explainer.explain(features) if request.include_explanation else None
        return build_response(final_score, confidence, explanation)
```

---

## Model Loading

**File:** `inference/model_loader.py`

```python
class ModelLoader:
    def load_all(self):
        self.classical_models = self._load_classical()   # pickle → dict of models
        self.onnx_session = self._load_onnx()            # ORT InferenceSession
        self.tokenizer = self._load_tokenizer()          # local tokenizer
        self.meta_learner = self._load_meta()            # stacking LR
        self.feature_extractor = self._load_extractor()  # TF-IDF etc.
```

If any model file is missing:
- Logs a warning
- Falls back to heuristic scoring
- Server still starts (no crash)

---

## Error Handling

| HTTP Code | Cause | Response |
|---|---|---|
| 422 | Invalid request body (Pydantic) | `{"detail": [...]}` |
| 429 | Rate limit exceeded | `{"error": "rate_limit"}` |
| 500 | Analysis pipeline error | `{"error": "Analysis failed"}` |

Global exception handler logs full traceback via Loguru and returns 500.

---

## Logging

Using **Loguru** for structured logging:
```
2024-01-15 10:23:41 | INFO | analyze:64 - [analyze] risk=phishing score=0.847 confidence=0.931 duration=1243ms
```

Log format: `{time} | {level} | {module}:{line} - {message}`
