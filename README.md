# 🛡️ TrustMail — AI Email Threat Detector

> **Privacy-first phishing detection. 100% local inference — your emails never leave your device.**

[![Version](https://img.shields.io/badge/version-1.1.0-blue.svg)](extension/manifest.json)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![MV3](https://img.shields.io/badge/Chrome-Manifest%20V3-orange.svg)](https://developer.chrome.com/docs/extensions/mv3/)
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://python.org)

---

## What is TrustMail?

TrustMail is a Chrome Extension that uses **locally running machine learning models** to detect phishing emails before you click anything dangerous. No cloud. No API keys. No data leaving your computer.

| Email Risk Level | Indicator | Meaning |
|---|---|---|
| 🟢 Safe | Green pill | No significant threats detected |
| 🟡 Low Risk | Yellow pill | Minor concerns — proceed carefully |
| 🟠 Suspicious | Orange pill | Multiple indicators — verify sender |
| 🔴 Phishing | Red pill | High-confidence attack — do not interact |
| ⚫ Highly Dangerous | Dark pill | Critical threat — delete immediately |

---

## Key Features

### 🆕 v1.1 — Inbox Risk Indicators
Risk pills appear **directly in your inbox** — no need to open an email to know it's dangerous.

- **Real-time scanning** of every email row as you browse
- **Hover tooltip** shows risk level, confidence %, and top threat reasons
- **Dynamic updates** as new emails arrive or you scroll
- Works in Gmail, Outlook, Yahoo Mail, and ProtonMail

### Core Features
- **4-stage hybrid AI pipeline**: Feature engineering → Classical ensemble → DistilBERT (ONNX) → SHAP explanations
- **Full report popup**: Risk meter, header analysis, URL breakdown, model predictions, history
- **Explainability**: SHAP feature importance + top reasons in plain English
- **Privacy by design**: Zero telemetry, zero cloud inference, zero email storage

---

## Architecture

```
Chrome Extension (MV3)
    ├─ inbox-scanner.js     ← Inbox risk indicator engine
    ├─ gmail.js / outlook.js / yahoo.js / proton.js
    ├─ service-worker.js    ← API proxy + 5-min cache
    └─ popup / options

Local TrustMail Backend (FastAPI + Python — CPU only, no GPU)
    ├─ Feature Engineering  ← 256-dim: stylometry, URL, header, keywords
    ├─ Classical Ensemble   ← RF + XGBoost + LightGBM + CatBoost + LR
    ├─ Signal Combination   ← header + URL + NLP weighted blend
    └─ Explainability       ← SHAP TreeExplainer + LIME
```

> **No deep learning.** No ONNX, no PyTorch, no GPU needed. Runs fully on CPU with scikit-learn, xgboost, lightgbm, and catboost.

See [docs/architecture.md](docs/architecture.md) for full diagrams.

---

## Installation

### Prerequisites
- Python 3.10+
- Google Chrome 112+

### 1. Start the backend

> **Note:** The pre-trained model files (`.pkl`, `.onnx`) and the raw datasets (`base_data/`) are excluded from this repository to keep it lightweight. You must generate or download them before running the server.

Choose one of the two options below to set up your models:

#### Option A: Quick Start (Synthetic Data)
If you want to test the application quickly without downloading large datasets:
```bash
cd TrustMail\backend

# Install dependencies
pip install -r requirements.txt
pip install xgboost lightgbm catboost

# Run training (automatically generates synthetic data as a fallback)
python training/run_training.py

# Start the server
python app.py
# ✅ Server running at http://127.0.0.1:8000
```

#### Option B: Full Setup (Real Datasets)
To train the models on the complete real-world phishing datasets (CEAS, Enron, Ling, etc.):
```bash
cd TrustMail\backend

# Install dependencies including training libraries
pip install -r requirements.txt
pip install -r requirements-training.txt

# 1. Download raw public datasets (SpamAssassin, UCI, etc.)
python datasets/download_datasets.py

# 2. Place any other custom datasets (e.g., CEAS_08.csv) in the `base_data/` folder in the root directory.

# 3. Preprocess and split the datasets
python training/preprocess_real_data.py

# 4. Train the models on the processed real data
python training/run_training.py --use-real-data

# Start the server
python app.py
# ✅ Server running at http://127.0.0.1:8000
```

### 2. Load the extension

1. Open Chrome → `chrome://extensions/`
2. Enable **Developer mode** (toggle top-right)
3. Click **Load unpacked**
4. Select the **`extension/`** folder
5. 🛡️ TrustMail icon appears in your toolbar

### 3. Verify it's working

- Open `http://127.0.0.1:8000/docs` — you should see the interactive API docs
- Open Gmail — you should see colored pills appear next to emails in your inbox
- Click the TrustMail toolbar icon — the status pill should show **Online**

---

## Usage

### Inbox View
Colored risk pills appear automatically next to every email subject in your inbox. **Hover** over a pill to see the tooltip. **Click** a pill to open the full TrustMail report.

### Open Email View
When you open an email, TrustMail automatically runs a full AI analysis and shows a floating badge in the bottom-right corner of the screen.

### Popup Dashboard
Click the TrustMail 🛡️ icon in your Chrome toolbar to see the full report for the currently open email, including:
- Animated risk score ring
- Header analysis (SPF/DKIM/DMARC)
- URL risk breakdown
- AI model predictions
- SHAP explanations
- Scan history

### Options
Right-click the TrustMail icon → **Options**, or visit the extension settings page to configure:
- Backend URL
- Auto-scan toggle
- Explanation depth
- Phishing notifications
- History retention

---

## Configuration

The backend is configured via environment variables or a `.env` file:

```env
TRUSTMAIL_HOST=127.0.0.1
TRUSTMAIL_PORT=8000
TRUSTMAIL_LOG_LEVEL=INFO
TRUSTMAIL_HEURISTIC_FALLBACK=true
```

The extension is configured through the Options page. No config files needed.

---

## Development

```bash
# Run backend in dev mode (auto-reload)
cd backend
uvicorn api.app:create_app --factory --reload --port 8000

# Build extension (TypeScript source)
cd extension
npm install && npm run build
```

See [docs/developer-guide.md](docs/developer-guide.md) for:
- Training models
- Adding new email providers
- Packaging for Chrome Web Store

---

## Documentation

| Doc | Contents |
|---|---|
| [Architecture](docs/architecture.md) | System design, data flow, Mermaid diagrams |
| [Machine Learning](docs/ml-documentation.md) | Models, features, training, ONNX pipeline |
| [Email Analysis Workflow](docs/email-analysis-workflow.md) | Complete lifecycle with flow diagrams |
| [Extension Guide](docs/extension-documentation.md) | MV3, service worker, content scripts |
| [Backend Guide](docs/backend-documentation.md) | FastAPI, routes, services |
| [Security](docs/security-documentation.md) | Privacy, CSP, threat model |
| [Developer Guide](docs/developer-guide.md) | Setup, training, adding providers |
| [API Reference](docs/api-documentation.md) | All endpoints with examples |
| [Performance](docs/performance-documentation.md) | Startup, caching, optimization |

---

## Privacy Guarantee

- ✅ **Zero cloud AI** — all inference runs on your machine via ONNX Runtime
- ✅ **Zero telemetry** — no analytics, no tracking, no external connections
- ✅ **Zero email storage** — raw email content is analyzed in memory only
- ✅ **Loopback only** — backend binds to 127.0.0.1 and cannot reach the internet
- ✅ **Open source** — inspect every line of code yourself

---

## Supported Email Providers

| Provider | Inbox Indicators | Full Analysis |
|---|---|---|
| Gmail | ✅ | ✅ |
| Outlook (Live, Office, 365) | ✅ | ✅ |
| Yahoo Mail | ✅ | ✅ |
| ProtonMail | ✅ | ✅ |

---

## License

MIT License — see [LICENSE](LICENSE) for details.
