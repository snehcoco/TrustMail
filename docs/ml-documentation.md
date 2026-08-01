# TrustMail — Machine Learning Documentation

## Model Overview

TrustMail uses a **3-stage classical ML pipeline** for fast, CPU-only, local phishing detection.
There are **no deep learning models** — no PyTorch, no ONNX, no GPU required.

```
Input Email
    │
    ▼
┌──────────────────────────────────┐
│  Stage 1: Feature Engineering    │
│                                  │
│  • Stylometric features          │
│  • URL aggregate features        │
│  • Sender/Reply-To features      │
│  • Punctuation patterns          │
│  • Keyword indicators (25 terms) │
│                                  │
│  Output: 256-dim float32 vector  │
└─────────────────┬────────────────┘
                  │
                  ▼
┌──────────────────────────────────┐
│  Stage 2: Classical Ensemble     │
│                                  │
│  • Random Forest   (30% weight)  │
│  • XGBoost         (28% weight)  │
│  • LightGBM        (22% weight)  │
│  • CatBoost        (12% weight)  │
│  • Logistic Reg.   ( 8% weight)  │
│                                  │
│  Weighted average of all probs   │
└─────────────────┬────────────────┘
                  │
                  ▼
┌──────────────────────────────────┐
│  Stage 3: Risk Scoring +         │
│           Signal Combination     │
│                                  │
│  ensemble_score × 0.50           │
│  + header_score × 0.20           │
│  + url_score    × 0.15           │
│  + attachment   × 0.10           │
│  + nlp_score    × 0.05           │
│                                  │
│  + SHAP/LIME Explainability      │
└─────────────────┬────────────────┘
                  │
                  ▼
          Risk Assessment
```

---

## Stage 1 — Feature Engineering

### Feature Groups

| Group | Size | Features |
|---|---|---|
| Stylometric | 20 | word count, sentence count, avg word/sentence length, lexical diversity, Flesch score, Gunning Fog, caps ratio, syllables |
| URL | 15 | url count, http/https ratio, IP-based URLs, encoded chars, avg/max URL length, suspicious TLDs |
| Sender/Header | 10 | sender present, domain present, free provider, reply-to mismatch |
| Punctuation | 10 | `!`, `?`, `$`, `%`, `@`, `...`, ALL CAPS words, `:`, `;` |
| Keywords | 25 | password, account, verify, confirm, urgent, suspended, click here, login, secure, update, bank, credit card, paypal, bitcoin, gift card, wire transfer, invoice, tax refund, congratulations, winner, prize, free, limited time, act now, irs |
| **Total** | **256** | Padded to fixed dimension |

### Key Phishing Indicators

| Feature | Why it matters |
|---|---|
| `reply_to_mismatch` | Phishers use different reply-to to capture credentials |
| `ip_based_url_ratio` | Phishers avoid registered domains → use raw IPs |
| `suspicious_tld_ratio` | `.xyz`, `.tk`, `.ml`, `.cf`, `.gq` are common free/disposable TLDs |
| `url_encoded_ratio` | `%20`-encoded URLs evade simple pattern matching |
| `caps_ratio` | URGENCY SIGNALING is a social engineering hallmark |
| `keyword: urgent` | Found in 87% of phishing emails |
| `keyword: verify` | Credential harvesting indicator |

### Heuristic Fallback (No Models Loaded)

When no trained models are available, TrustMail runs purely rule-based scoring:

```
NLP pattern matching  →  nlp_score  (urgency, credential harvesting, fear tactics)
URL analysis          →  url_score  (homographs, IP URLs, shortened links)
Header analysis       →  header_score (SPF/DKIM/DMARC, reply-to mismatch)

final_score = ensemble(0) × 0.50 + header × 0.20 + url × 0.15 + attach × 0.10 + nlp × 0.05
confidence  = min(|final_score - 0.5| × 2, 0.75)   ← capped at 75% (less reliable)
```

---

## Stage 2 — Classical Ensemble

### Models

| Model | Weight | Key Strength |
|---|---|---|
| **Random Forest** | 30% | Robust to noise, resistant to overfitting on tabular data |
| **XGBoost** | 28% | Excellent on sparse keyword features, handles imbalance |
| **LightGBM** | 22% | Fast training, low memory, good on high-dimensional features |
| **CatBoost** | 12% | Native handling of categorical-like binary features |
| **Logistic Regression** | 8% | Calibrated probabilities, interpretable baseline |

### Why No Deep Learning?

| Concern | Classical ML Answer |
|---|---|
| **Privacy** | No model requires external API calls or cloud inference |
| **Speed** | All 5 models combined run in <20ms on CPU |
| **Memory** | Full ensemble uses ~50–150 MB RAM |
| **Dependencies** | scikit-learn, xgboost, lightgbm, catboost — no PyTorch/CUDA |
| **Interpretability** | SHAP TreeExplainer gives exact Shapley values in <500ms |
| **Maintenance** | No fine-tuning datasets, tokenizers, or ONNX exports needed |

### Weight Normalization (Partial Ensemble)

If some models fail to load, weights are renormalized:
```python
ensemble_prob = weighted_sum / total_weight  # total_weight = sum of loaded models' weights
```
This means the ensemble still works correctly with just 1–4 models loaded.

### Training Hyperparameters

```python
RandomForestClassifier(n_estimators=300, max_depth=20, min_samples_split=4,
                       class_weight="balanced", n_jobs=-1, random_state=42)

XGBClassifier(n_estimators=300, max_depth=6, learning_rate=0.1,
              subsample=0.8, colsample_bytree=0.8, eval_metric="logloss")

LGBMClassifier(n_estimators=300, max_depth=8, learning_rate=0.05,
               subsample=0.8, colsample_bytree=0.8, class_weight="balanced")

CatBoostClassifier(iterations=300, depth=8, learning_rate=0.05,
                   auto_class_weights="Balanced", verbose=False)

LogisticRegression(C=1.0, max_iter=2000, class_weight="balanced", solver="lbfgs")
```

---

## Stage 3 — Risk Scoring

### Signal Combination
```python
final_score = (
    ensemble_score * 0.50   # ML models have highest weight
  + header_score  * 0.20   # SPF/DKIM/DMARC failures are strong signals
  + url_score     * 0.15   # Homograph/IP/shortened URLs
  + attachment_score * 0.10
  + nlp_score     * 0.05   # Pattern matching (weakest signal)
)
```

### Risk Thresholds

| Score Range | Risk Level | Emoji | Meaning |
|---|---|---|---|
| 0.00 – 0.20 | `safe` | 🟢 | No significant threat indicators |
| 0.20 – 0.45 | `low_risk` | 🟡 | Minor concerns; proceed carefully |
| 0.45 – 0.65 | `suspicious` | 🟠 | Multiple indicators; verify sender |
| 0.65 – 0.85 | `phishing` | 🔴 | High-confidence phishing attempt |
| 0.85 – 1.00 | `highly_dangerous` | ⚫ | Critical threat; delete immediately |

### Confidence Scoring

```python
# Models loaded — confidence = certainty of the ensemble decision
confidence = abs(ensemble_prob - 0.5) * 2.0   # [0.0 → 1.0]

# No models (heuristic mode) — confidence from rule signal strength
confidence = min(abs(final_score - 0.5) * 2.0, 0.75)   # capped at 75%
```

A score of **0.90** → confidence = `|0.90 - 0.5| × 2 = 0.80` (80% confident)
A score of **0.52** → confidence = `|0.52 - 0.5| × 2 = 0.04` (uncertain, near boundary)

---

## Explainability Pipeline

### SHAP (Global — Which features drove the score?)

- Uses `TreeExplainer` for RF/XGB/LGB/CatBoost — exact, fast
- Returns `top_features` with direction (`phishing` / `safe`) and magnitude
- Runs in <500ms for all tree models combined

### LIME (Local — Which words in this email triggered it?)

- Perturbs input text 300 times
- Trains a local linear model on perturbations
- Returns word-level contributions (positive = more phishing, negative = more safe)
- Uses best available classical model as oracle

### Output format
```json
{
  "shap_explanation": {
    "top_features": [
      { "feature": "reply_to_mismatch", "importance": 0.312, "direction": "phishing" },
      { "feature": "url_count",         "importance": 0.241, "direction": "phishing" },
      { "feature": "lexical_diversity", "importance": -0.187, "direction": "safe" }
    ]
  },
  "top_reasons": [
    "Reply-To mismatch detected",
    "High number of external URLs",
    "Urgent language: 'act now', 'verify'"
  ]
}
```

---

## Training

### Run training (one command)
```bash
cd backend
python training/run_training.py
```

This generates **8,000 synthetic emails** (4k phishing + 4k safe), extracts features, trains all 5 models, and saves the bundle.

**No external dataset download required.**

### Output files
```
trained_models/
  ensemble_classical.pkl   # All 5 trained models (dict)
  feature_scaler.pkl       # StandardScaler for numeric features
  label_encoder.pkl        # LabelEncoder (0=safe, 1=phishing)
  training_report.txt      # Per-model AUC + classification report
```

### Dataset Generation

The synthetic generator creates realistic emails with:
- 25 phishing subject templates × body variants
- 14 phishing sender templates (homograph domains, disposable TLDs)
- 12 phishing URL templates (IP-based, shortened, suspicious TLDs)
- 20 safe subject templates × body variants
- 14 safe sender templates (real companies: fedex, amazon, github, etc.)
- Per-email random variation in urgency phrases and URL count

### Validation Performance (Expected)

On the 15% held-out validation set with synthetic data:

| Model | Expected AUC |
|---|---|
| Random Forest | >0.97 |
| XGBoost | >0.97 |
| LightGBM | >0.97 |
| CatBoost | >0.96 |
| Logistic Regression | >0.93 |

> **Note:** Real-world performance will differ from synthetic validation metrics.
> For production use, supplement with real labeled datasets (PhishTank, CEAS 2008, Enron).
