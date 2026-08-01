# TrustMail — Developer Guide

## Prerequisites

| Tool | Minimum Version | Install |
|---|---|---|
| Python | 3.10+ | python.org |
| pip | 23+ | Included with Python |
| Chrome | 112+ | chrome.com |
| Node.js | 18+ (optional) | For TypeScript build only |
| Git | 2.x | git-scm.com |

---

## Initial Setup

### 1. Clone the repository
```bash
git clone https://github.com/your-org/trustmail.git
cd trustmail
```

### 2. Create Python virtual environment
```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# Linux/Mac
source .venv/bin/activate
```

### 3. Install backend dependencies
```bash
cd backend
pip install -r requirements.txt
```

If you want to train models locally:
```bash
pip install -r requirements-training.txt
```

### 4. Start the backend
```bash
python app.py
# Server starts at http://127.0.0.1:8000
# Visit http://127.0.0.1:8000/docs for interactive API docs
```

> **Note:** The backend starts in heuristic mode if no trained models are found. Full AI analysis requires trained model files.

### 5. Load the extension
1. Open Chrome → `chrome://extensions/`
2. Enable **Developer mode** (top right)
3. Click **Load unpacked**
4. Select the `extension/` directory
5. TrustMail icon appears in toolbar

---

## Directory Structure

```
TrustMail/
├── extension/               Chrome Extension (load this folder)
│   ├── manifest.json        Extension manifest (MV3)
│   ├── background/
│   │   └── service-worker.js
│   ├── content/
│   │   ├── inbox-scanner.js  ← NEW: Shared inbox indicator engine
│   │   ├── gmail.js
│   │   ├── outlook.js
│   │   ├── yahoo.js
│   │   └── proton.js
│   ├── popup/
│   │   ├── index.html
│   │   └── popup.js
│   ├── options/
│   │   ├── index.html
│   │   └── options.js
│   └── assets/
│       └── icons/
│
├── backend/                 FastAPI backend
│   ├── app.py               Uvicorn entry point
│   ├── api/                 Routes, schemas, services
│   ├── inference/           ONNX runner, model loader
│   ├── preprocessing/       Feature extraction
│   ├── training/            Training scripts
│   ├── config/              Settings and YAML config
│   └── trained_models/      Model files (git-ignored)
│
├── docs/                    ← This documentation
└── scripts/                 Helper scripts
```

---

## Training Models

### Dataset Preparation
```bash
# Place datasets in backend/datasets/
# Required files:
#   phishing.csv   — columns: text, label (1=phishing, 0=safe)
#   legit.csv      — legitimate email samples
```

### Train Classical Ensemble
```bash
cd backend
python training/train_classical.py \
  --data datasets/ \
  --output trained_models/ \
  --cv-folds 5
```

Output: `trained_models/ensemble_classical.pkl`

### Fine-tune DistilBERT
```bash
python training/train_transformer.py \
  --data datasets/ \
  --model distilbert-base-uncased \
  --epochs 3 \
  --batch-size 8 \
  --output trained_models/
```

Output:
- `trained_models/distilbert_phishing.onnx`
- `trained_models/tokenizer.json`

### Export to ONNX (if retraining transformer)
```bash
python training/export_onnx.py \
  --model trained_models/distilbert_phishing.pt \
  --output trained_models/distilbert_phishing.onnx \
  --optimize
```

---

## Replacing Models

### Classical Models
1. Train new models and save as pickle
2. Update paths in `config/model_config.yaml`
3. Restart backend — `ModelLoader.load_all()` picks up new files

### Transformer Model
1. Export new model to ONNX format
2. Place at `trained_models/distilbert_phishing.onnx`
3. Verify tokenizer compatibility at `trained_models/tokenizer.json`
4. Restart backend

### Thresholds
Edit `config/model_config.yaml`:
```yaml
risk_thresholds:
  safe: 0.20
  low_risk: 0.40
  suspicious: 0.65
  phishing: 0.85
  highly_dangerous: 1.01
```

---

## Adding a New Email Provider

### Step 1: Create content script
```javascript
// extension/content/myprovider.js
'use strict';
(function () {
  if (window.__trustmailMyProviderLoaded) return;
  window.__trustmailMyProviderLoaded = true;

  let lastSubject = null;
  let lastResult = null;

  chrome.runtime.onMessage.addListener((req, sender, sendResponse) => {
    if (req.type === 'GET_CURRENT_RESULT') {
      sendResponse({ success: true, data: lastResult });
    }
    return false;
  });

  // ... full email open detection (see gmail.js for reference) ...

  // ── Inbox Risk Indicator ────────────────────────────────────
  function myProviderExtract(row) {
    const subjectEl = row.querySelector('.my-subject-selector');
    const subject = subjectEl?.textContent?.trim() || '';
    const sender = row.querySelector('.my-sender-selector')?.textContent?.trim() || '';
    return {
      subject, sender, urls: [],
      platform: 'myprovider',
      emailId: btoa(subject + sender).slice(0, 20),
      subjectEl,
    };
  }

  function activate() {
    if (!window.__tmScanner) { setTimeout(activate, 300); return; }
    window.__tmScanner.observe({
      rowSelector: '.my-inbox-row-selector',
      extractFn: myProviderExtract,
    });
  }
  activate();

  console.log('[TrustMail] MyProvider content script loaded ✓');
})();
```

### Step 2: Add to manifest.json
```json
{
  "matches": ["https://mail.myprovider.com/*"],
  "js": ["content/inbox-scanner.js", "content/myprovider.js"],
  "run_at": "document_idle",
  "all_frames": false
}
```

Also add to `host_permissions`:
```json
"https://mail.myprovider.com/*"
```

### Step 3: Reload extension in Chrome

---

## Building the Extension (TypeScript → JS)

The `extension/content/*.js` and `popup/popup.js` are the plain-JS dev build. The TypeScript source lives in `extension/content/*.ts` and is compiled with Vite.

```bash
cd extension
npm install
npm run build
# Output: extension/dist/
```

Copy dist files for direct Chrome loading:
```bash
npm run dev:copy
# Or manually: copy extension/dist/ → extension/ (overwrite .js files)
```

---

## Packaging the Extension for Distribution

```bash
# Build production bundle
cd extension && npm run build

# Create .zip for Chrome Web Store
cd ..
powershell -Command "Compress-Archive -Path extension\* -DestinationPath trustmail-v1.1.0.zip"
```

Upload `trustmail-v1.1.0.zip` to [Chrome Web Store Developer Console](https://chrome.google.com/webstore/devconsole/).

---

## Testing Workflow

### Backend Tests
```bash
cd backend
pytest tests/ -v
pytest tests/test_analyze.py -v          # Analyze endpoint
pytest tests/test_feature_extractor.py   # Feature pipeline
```

### Extension Testing
1. Load extension in Chrome
2. Open Gmail → verify inbox pills appear on email rows
3. Hover a pill → verify tooltip shows risk data
4. Click a pill → verify popup opens with pre-loaded result
5. Open an email → verify floating badge appears
6. Click TrustMail icon → verify full report popup shows
7. Check Settings page → test connection → should show "Connected"

### Regression Checklist
- [ ] Existing floating badge still shows when email is opened
- [ ] Popup shows full report when opened from toolbar icon
- [ ] Options page saves and loads settings
- [ ] Scan history is stored and clearable
- [ ] Export JSON/Text downloads work

---

## Common Issues

| Problem | Solution |
|---|---|
| Backend `{"detail":"Not Found"}` on `/` | Normal in older builds — now redirects to `/docs` |
| Extension CSP error: inline script | Ensure all JS is in `.js` files, not in `<script>` blocks in HTML |
| No pills appearing in inbox | Check DevTools → Console for `[TrustMail]` messages; verify backend is running |
| `Could not load background script ''` | Check `manifest.json` → `background.service_worker` path is set |
| Models not loading | Ensure `trained_models/` directory exists; heuristic fallback will activate |
| Outlook pills not appearing | Outlook updates class names frequently; may need selector update |
