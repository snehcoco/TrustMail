# TrustMail Backend

> Privacy-first AI email threat detection — 100% local inference.

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Start server (auto-launches FastAPI via uvicorn)
python app.py
# Server available at: http://127.0.0.1:8000
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/analyze` | Analyze single email |
| POST | `/api/v1/batch` | Analyze multiple emails |
| POST | `/api/v1/headers` | Headers-only analysis |
| POST | `/api/v1/urls` | URL threat analysis |
| POST | `/api/v1/attachments` | Attachment metadata analysis |
| POST | `/api/v1/explain` | SHAP + LIME explanation |
| GET | `/health` | Health check |
| GET | `/version` | Version info |
| GET | `/metrics` | Performance metrics |
| GET | `/status` | Loaded models status |

## Training Pipeline

```bash
# 1. Install training deps
pip install -r requirements-training.txt

# 2. Download public datasets
python datasets/download_datasets.py --datasets sample

# 3. Preprocess
python datasets/preprocess_datasets.py

# 4. Train classical models (RF, XGB, LightGBM, etc.)
python training/train_classical.py

# 5. Fine-tune DistilBERT (GPU recommended)
python training/train_transformer.py --model distilbert --epochs 3

# 6. Export to ONNX
python training/export_onnx.py \
  --model-dir trained_models/transformer_finetuned \
  --output trained_models/distilbert_phishing.onnx \
  --quantize
```

## Testing

```bash
pytest tests/ -v --cov=. --cov-report=html
```

## Docker

```bash
docker build -t trustmail-backend .
docker run -p 8000:8000 -v ./trained_models:/app/trained_models trustmail-backend
```

## Project Structure

```
backend/
├── app.py                     # Entry point (python app.py)
├── config/
│   ├── settings.py            # Pydantic settings
│   └── model_config.yaml      # Model thresholds & weights
├── api/
│   ├── app.py                 # FastAPI application factory
│   ├── routes/                # API route handlers
│   ├── services/              # Business logic
│   ├── explainability/        # SHAP + LIME
│   ├── schemas/               # Request/response models
│   └── middleware/            # CORS, rate limiting, audit
├── inference/
│   ├── onnx_runner.py         # ONNX Runtime wrapper
│   └── model_loader.py        # Lazy model loader
├── preprocessing/
│   ├── text_cleaner.py        # Text normalization
│   └── feature_extractor.py  # Feature engineering
├── training/
│   ├── train_classical.py     # Classical ML training
│   ├── train_transformer.py   # DistilBERT fine-tuning
│   └── export_onnx.py         # ONNX export + quantization
├── datasets/                  # Dataset scripts + sample data
├── tests/                     # pytest test suite
├── trained_models/            # Saved models (gitignored)
├── requirements.txt           # Runtime dependencies
├── requirements-training.txt  # Training dependencies
└── Dockerfile                 # Multi-stage Docker build
```
