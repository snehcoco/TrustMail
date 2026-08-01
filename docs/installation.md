# TrustMail Installation Guide

## Prerequisites

| Tool | Version | Required For |
|------|---------|-------------|
| Python | 3.10+ | Backend |
| pip | 23+ | Backend dependencies |
| Node.js | 20+ | Extension |
| npm | 10+ | Extension dependencies |
| Chrome | 120+ | Extension |
| Docker | 24+ (optional) | Containerized deployment |

---

## Quick Start (Recommended)

### 1. Clone & Setup

```bash
git clone https://github.com/your-org/trustmail.git
cd TrustMail
```

### 2. Start the Backend

```bash
cd backend
pip install -r requirements.txt
python app.py
```

The server starts at **http://127.0.0.1:8000**.

Verify: `curl http://127.0.0.1:8000/health`

### 3. Build the Extension

```bash
cd extension
npm install
npm run build
```

### 4. Load in Chrome

1. Open `chrome://extensions/`
2. Enable **Developer Mode** (top right toggle)
3. Click **Load unpacked**
4. Select `extension/dist/`
5. The TrustMail shield icon appears in your toolbar

### 5. Test It

Open Gmail and click on any email. You should see:
- A floating badge showing the risk level
- Click the TrustMail icon to open the full dashboard

---

## Backend with Docker

```bash
# Build and start
docker-compose up --build

# Or just start (requires pre-built image)
docker-compose up
```

The API will be available at `http://127.0.0.1:8000`.

---

## Training Models (Optional)

If you want to train your own models:

```bash
cd backend

# 1. Install training deps
pip install -r requirements-training.txt

# 2. Download datasets
python datasets/download_datasets.py --datasets sample

# 3. Preprocess
python datasets/preprocess_datasets.py

# 4. Train classical models
python training/train_classical.py

# 5. Train transformer (requires GPU for reasonable speed)
python training/train_transformer.py --model distilbert

# 6. Export to ONNX
python training/export_onnx.py \
  --model-dir trained_models/transformer_finetuned \
  --output trained_models/distilbert_phishing.onnx \
  --quantize
```

---

## Environment Variables

Create `backend/.env` to override defaults:

```env
HOST=127.0.0.1
PORT=8000
RELOAD=false
WORKERS=1
LOG_LEVEL=INFO
SECRET_KEY=your-secret-key-here
ENABLE_TELEMETRY=false
LOG_EMAIL_CONTENT=false
```

---

## Troubleshooting

### "Backend offline" in extension
1. Verify backend is running: `curl http://127.0.0.1:8000/health`
2. Check firewall isn't blocking port 8000
3. Try `python app.py` from the `backend/` directory

### No badge appears on Gmail
1. Verify extension is loaded and enabled
2. Reload Gmail (Ctrl+F5)
3. Check Chrome console for errors (F12 → Console)

### Models not loaded
1. Run training pipeline first, or
2. Download pre-trained models (coming soon)
3. Check `backend/trained_models/` directory

### Low accuracy
1. Retrain with more data from `datasets/download_datasets.py`
2. See [Training Guide](training-guide.md)
