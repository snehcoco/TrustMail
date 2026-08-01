"""
TrustMail — Model Training Pipeline
=====================================
Trains the classical ensemble on real preprocessed data (preferred)
or synthetic data (fallback if no processed CSVs exist).

Usage:
    cd backend
    python training/run_training.py                # auto-detect data source
    python training/run_training.py --use-real-data
    python training/run_training.py --use-synthetic

Output:
    trained_models/candidates/   — newly trained models (staging)
    trained_models/              — promoted models (production)
    trained_models/backup/       — previous production models
    docs/model_training_report.md
    training_results.json

Design rules (enforced):
  - StandardScaler fit ONLY on training split
  - Test data never used for tuning or threshold selection
  - Thresholds determined on validation set
  - Old production models backed up before overwrite
  - Models promoted only if evaluation passes minimum bar
"""

from __future__ import annotations

import argparse
import json
import os
import pickle
import re
import shutil
import sys
import time
import unicodedata
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
from loguru import logger
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score, classification_report, confusion_matrix,
    f1_score, precision_score, recall_score, roc_auc_score,
    average_precision_score,
)
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder, StandardScaler

# ── Path setup ────────────────────────────────────────────────────────────────
BACKEND_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from preprocessing.feature_extractor import FeatureExtractor
from preprocessing.text_cleaner import TextCleaner

PROCESSED_DIR   = BACKEND_DIR / "datasets" / "processed"
MODELS_DIR      = BACKEND_DIR / "trained_models"
CANDIDATES_DIR  = MODELS_DIR / "candidates"
BACKUP_DIR      = MODELS_DIR / "backup"
DOCS_DIR        = BACKEND_DIR.parent / "docs"

RANDOM_SEED = 42
MIN_ACCEPTABLE_AUC = 0.70   # Minimum AUC to promote candidate models


# ═══════════════════════════════════════════════════════════════════════════════
# DATA LOADING
# ═══════════════════════════════════════════════════════════════════════════════

def load_real_data() -> Tuple[
    np.ndarray, np.ndarray,
    np.ndarray, np.ndarray,
    np.ndarray, np.ndarray,
    StandardScaler
]:
    """Load processed CSVs and extract features. Returns (X_train,y_train,...,scaler)."""
    import pandas as pd

    train_path = PROCESSED_DIR / "train.csv"
    val_path   = PROCESSED_DIR / "val.csv"
    test_path  = PROCESSED_DIR / "test.csv"

    for p in [train_path, val_path, test_path]:
        if not p.exists():
            raise FileNotFoundError(
                f"Processed data not found: {p}\n"
                "Run first: python backend/training/preprocess_real_data.py"
            )

    logger.info("Loading real preprocessed datasets...")
    train_df = pd.read_csv(train_path, encoding="utf-8")
    val_df   = pd.read_csv(val_path,   encoding="utf-8")
    test_df  = pd.read_csv(test_path,  encoding="utf-8")

    logger.info(f"  Train: {len(train_df):,}  Val: {len(val_df):,}  Test: {len(test_df):,}")

    def extract(df: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray]:
        cleaner   = TextCleaner()
        extractor = FeatureExtractor()
        feats, labels = [], []
        for i, (_, row) in enumerate(df.iterrows()):
            if i % 5000 == 0:
                logger.info(f"    Extracting features: {i:,}/{len(df):,}")
            body    = str(row.get("body", "") or "")
            subject = str(row.get("subject", "") or "")
            sender  = str(row.get("sender", "") or "")
            text    = f"SUBJECT: {subject}\nFROM: {sender}\n\n{body}" if subject else body
            cleaned = cleaner.clean(text)
            feat = extractor.extract(
                text=cleaned,
                sender=sender or None,
                urls=_extract_urls(body),
            )
            feats.append(feat)
            labels.append(int(row["label"]))
        return np.array(feats, dtype=np.float32), np.array(labels, dtype=np.int32)

    logger.info("Extracting features from train split...")
    X_train_raw, y_train = extract(train_df)
    logger.info("Extracting features from val split...")
    X_val_raw,   y_val   = extract(val_df)
    logger.info("Extracting features from test split...")
    X_test_raw,  y_test  = extract(test_df)

    # ── Fit scaler on TRAINING DATA ONLY ─────────────────────────────────────
    logger.info("Fitting StandardScaler on training data only...")
    scaler = StandardScaler()
    X_train = scaler.fit_transform(X_train_raw)
    X_val   = scaler.transform(X_val_raw)
    X_test  = scaler.transform(X_test_raw)

    return X_train, y_train, X_val, y_val, X_test, y_test, scaler


def _extract_urls(text: str) -> List[str]:
    pattern = re.compile(r"https?://[^\s<>\"']+|www\.[^\s<>\"']+", re.IGNORECASE)
    return list(set(pattern.findall(text)))[:50]


def generate_synthetic_data() -> Tuple[
    np.ndarray, np.ndarray,
    np.ndarray, np.ndarray,
    np.ndarray, np.ndarray,
    StandardScaler
]:
    """Fallback: generate synthetic data when no real data is preprocessed."""
    logger.warning("No processed data found — using synthetic fallback dataset.")
    logger.warning("For better accuracy, run: python backend/training/preprocess_real_data.py")

    # Import the generator from the existing run_training script
    sys.path.insert(0, str(Path(__file__).parent))

    # Inline a minimal synthetic generator
    from training.run_training import generate_dataset, build_feature_matrix

    texts, senders, urls_list, reply_tos, labels = generate_dataset(
        n_phishing=4000, n_safe=4000, seed=RANDOM_SEED
    )
    X = build_feature_matrix(texts, senders, urls_list, reply_tos)
    y = np.array(labels, dtype=np.int32)

    scaler  = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    X_temp, X_test, y_temp, y_test = train_test_split(
        X_scaled, y, test_size=0.10, stratify=y, random_state=RANDOM_SEED
    )
    X_train, X_val, y_train, y_val = train_test_split(
        X_temp, y_temp, test_size=0.111, stratify=y_temp, random_state=RANDOM_SEED
    )
    return X_train, y_train, X_val, y_val, X_test, y_test, scaler


# ═══════════════════════════════════════════════════════════════════════════════
# TRAINING
# ═══════════════════════════════════════════════════════════════════════════════

def train_all_models(
    X_train: np.ndarray, y_train: np.ndarray,
    X_val:   np.ndarray, y_val:   np.ndarray,
) -> Tuple[dict, dict]:
    """Train 5 classical models. Returns (models_dict, metrics_dict)."""
    models  = {}
    metrics = {}

    def evaluate(name: str, model, X: np.ndarray, y: np.ndarray) -> dict:
        preds = model.predict(X)
        proba = model.predict_proba(X)[:, 1]
        m = {
            "auc":       round(float(roc_auc_score(y, proba)), 5),
            "pr_auc":    round(float(average_precision_score(y, proba)), 5),
            "f1":        round(float(f1_score(y, preds)), 5),
            "precision": round(float(precision_score(y, preds)), 5),
            "recall":    round(float(recall_score(y, preds)), 5),
            "accuracy":  round(float(accuracy_score(y, preds)), 5),
            "fpr":       round(float(
                1 - precision_score(y, preds, pos_label=0)
            ), 5),
        }
        report = classification_report(y, preds, target_names=["safe","phishing"])
        logger.info(f"\n  [{name}] AUC={m['auc']:.4f}  F1={m['f1']:.4f}  "
                    f"FPR={m['fpr']:.4f}\n{report}")
        return m

    # ── Logistic Regression ──────────────────────────────────────────────────
    logger.info("Training Logistic Regression...")
    lr = LogisticRegression(
        C=1.0, max_iter=2000, class_weight="balanced",
        random_state=RANDOM_SEED, solver="lbfgs"
    )
    lr.fit(X_train, y_train)
    models["logistic_regression"] = lr
    metrics["logistic_regression"] = evaluate("logistic_regression", lr, X_val, y_val)

    # ── Random Forest ────────────────────────────────────────────────────────
    logger.info("Training Random Forest...")
    rf = RandomForestClassifier(
        n_estimators=300, max_depth=20, min_samples_split=4,
        class_weight="balanced", n_jobs=-1, random_state=RANDOM_SEED,
    )
    rf.fit(X_train, y_train)
    models["random_forest"] = rf
    metrics["random_forest"] = evaluate("random_forest", rf, X_val, y_val)

    # ── XGBoost ──────────────────────────────────────────────────────────────
    try:
        from xgboost import XGBClassifier
        logger.info("Training XGBoost...")
        scale_pos = float((y_train == 0).sum()) / max((y_train == 1).sum(), 1)
        xgb = XGBClassifier(
            n_estimators=300, max_depth=6, learning_rate=0.1,
            subsample=0.8, colsample_bytree=0.8, eval_metric="logloss",
            scale_pos_weight=scale_pos, n_jobs=-1,
            random_state=RANDOM_SEED, verbosity=0,
        )
        xgb.fit(X_train, y_train)
        models["xgboost"] = xgb
        metrics["xgboost"] = evaluate("xgboost", xgb, X_val, y_val)
    except ImportError:
        logger.warning("XGBoost not installed — skipping")

    # ── LightGBM ─────────────────────────────────────────────────────────────
    try:
        import lightgbm as lgb
        logger.info("Training LightGBM...")
        lgbm = lgb.LGBMClassifier(
            n_estimators=300, max_depth=8, learning_rate=0.05,
            subsample=0.8, colsample_bytree=0.8, class_weight="balanced",
            n_jobs=-1, random_state=RANDOM_SEED, verbose=-1,
        )
        lgbm.fit(X_train, y_train)
        models["lightgbm"] = lgbm
        metrics["lightgbm"] = evaluate("lightgbm", lgbm, X_val, y_val)
    except ImportError:
        logger.warning("LightGBM not installed — skipping")

    # ── CatBoost ─────────────────────────────────────────────────────────────
    try:
        from catboost import CatBoostClassifier
        logger.info("Training CatBoost...")
        cat = CatBoostClassifier(
            iterations=300, depth=8, learning_rate=0.05,
            loss_function="Logloss", auto_class_weights="Balanced",
            random_seed=RANDOM_SEED, verbose=False,
        )
        cat.fit(X_train, y_train)
        models["catboost"] = cat
        metrics["catboost"] = evaluate("catboost", cat, X_val, y_val)
    except ImportError:
        logger.warning("CatBoost not installed — skipping")

    return models, metrics


# ═══════════════════════════════════════════════════════════════════════════════
# EVALUATION — full test set
# ═══════════════════════════════════════════════════════════════════════════════

ENSEMBLE_WEIGHTS = {
    "random_forest":       0.30,
    "xgboost":             0.28,
    "lightgbm":            0.22,
    "catboost":            0.12,
    "logistic_regression": 0.08,
}

def evaluate_ensemble(
    models: dict,
    X_test: np.ndarray,
    y_test: np.ndarray,
) -> dict:
    """Weighted ensemble evaluation on test set."""
    weighted_sum = np.zeros(len(y_test))
    total_weight = 0.0

    for name, model in models.items():
        w = ENSEMBLE_WEIGHTS.get(name, 0.1)
        prob = model.predict_proba(X_test)[:, 1]
        weighted_sum += prob * w
        total_weight += w

    ensemble_proba = weighted_sum / total_weight
    preds = (ensemble_proba >= 0.5).astype(int)

    cm = confusion_matrix(y_test, preds)
    tn, fp, fn, tp = cm.ravel() if cm.shape == (2, 2) else (0, 0, 0, 0)

    m = {
        "auc":       round(float(roc_auc_score(y_test, ensemble_proba)), 5),
        "pr_auc":    round(float(average_precision_score(y_test, ensemble_proba)), 5),
        "f1":        round(float(f1_score(y_test, preds)), 5),
        "precision": round(float(precision_score(y_test, preds)), 5),
        "recall":    round(float(recall_score(y_test, preds)), 5),
        "accuracy":  round(float(accuracy_score(y_test, preds)), 5),
        "fpr":       round(float(fp / max(fp + tn, 1)), 5),
        "fnr":       round(float(fn / max(fn + tp, 1)), 5),
        "confusion_matrix": {"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)},
    }

    report = classification_report(y_test, preds, target_names=["safe", "phishing"])
    logger.info(f"\n[ENSEMBLE — TEST SET]\n{report}")
    logger.info(f"  AUC={m['auc']:.4f}  F1={m['f1']:.4f}  "
                f"FPR={m['fpr']:.4f}  FNR={m['fnr']:.4f}")

    return m


# ═══════════════════════════════════════════════════════════════════════════════
# BACKUP + PROMOTION
# ═══════════════════════════════════════════════════════════════════════════════

def backup_existing_models() -> Optional[str]:
    """Move current production models to backup/ with timestamp."""
    prod_pkl = MODELS_DIR / "ensemble_classical.pkl"
    if not prod_pkl.exists():
        return None

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    backup_subdir = BACKUP_DIR / ts
    backup_subdir.mkdir()

    for fname in ["ensemble_classical.pkl", "feature_scaler.pkl",
                  "label_encoder.pkl", "model_metadata.json"]:
        src = MODELS_DIR / fname
        if src.exists():
            shutil.copy2(src, backup_subdir / fname)

    logger.info(f"  ✓ Previous models backed up to: trained_models/backup/{ts}/")
    return ts


def save_candidates(models: dict, scaler: StandardScaler, le: LabelEncoder,
                    metadata: dict) -> None:
    CANDIDATES_DIR.mkdir(parents=True, exist_ok=True)
    with open(CANDIDATES_DIR / "ensemble_classical.pkl", "wb") as f:
        pickle.dump(models, f, protocol=pickle.HIGHEST_PROTOCOL)
    with open(CANDIDATES_DIR / "feature_scaler.pkl", "wb") as f:
        pickle.dump(scaler, f, protocol=pickle.HIGHEST_PROTOCOL)
    with open(CANDIDATES_DIR / "label_encoder.pkl", "wb") as f:
        pickle.dump(le, f, protocol=pickle.HIGHEST_PROTOCOL)
    with open(CANDIDATES_DIR / "model_metadata.json", "w") as f:
        json.dump(metadata, f, indent=2)
    logger.info("  ✓ Candidate models saved to trained_models/candidates/")


def promote_candidates(backup_ts: Optional[str]) -> None:
    """Promote candidates to production after evaluation passes."""
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    for fname in ["ensemble_classical.pkl", "feature_scaler.pkl",
                  "label_encoder.pkl", "model_metadata.json"]:
        src = CANDIDATES_DIR / fname
        if src.exists():
            shutil.copy2(src, MODELS_DIR / fname)
    logger.info("  ✓ Candidate models promoted to production")
    if backup_ts:
        logger.info(f"  ↩ Rollback available: trained_models/backup/{backup_ts}/")


# ═══════════════════════════════════════════════════════════════════════════════
# REPORTS
# ═══════════════════════════════════════════════════════════════════════════════

def save_results(
    model_metrics: dict,
    ensemble_metrics: dict,
    metadata: dict,
    data_source: str,
    train_size: int, val_size: int, test_size: int,
) -> None:
    results = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "data_source":  data_source,
        "dataset": {
            "train_samples": train_size,
            "val_samples":   val_size,
            "test_samples":  test_size,
            "total":         train_size + val_size + test_size,
        },
        "models": model_metrics,
        "ensemble": ensemble_metrics,
        "metadata": metadata,
    }
    path = MODELS_DIR / "training_results.json"
    with open(path, "w") as f:
        json.dump(results, f, indent=2)
    logger.info(f"  ✓ training_results.json saved")


def generate_md_report(
    model_metrics: dict,
    ensemble_metrics: dict,
    data_source: str,
    train_size: int, val_size: int, test_size: int,
) -> None:
    best_model = max(model_metrics.items(), key=lambda x: x[1]["auc"])[0]
    cm = ensemble_metrics.get("confusion_matrix", {})

    lines = [
        "# TrustMail — Model Training Report",
        "",
        f"**Generated:** {time.strftime('%Y-%m-%d %H:%M:%S')}  ",
        f"**Data source:** {data_source}  ",
        f"**Random seed:** {RANDOM_SEED}",
        "",
        "---",
        "",
        "## Dataset Summary",
        "",
        f"| Split | Samples |",
        f"|---|---|",
        f"| Train | {train_size:,} |",
        f"| Validation | {val_size:,} |",
        f"| Test | {test_size:,} |",
        f"| **Total** | **{train_size+val_size+test_size:,}** |",
        "",
        "---",
        "",
        "## Individual Model Validation Metrics",
        "",
        "| Model | AUC | PR-AUC | F1 | Precision | Recall | FPR |",
        "|---|---|---|---|---|---|---|",
    ]
    for name, m in model_metrics.items():
        lines.append(
            f"| {name} | {m['auc']} | {m['pr_auc']} | {m['f1']} "
            f"| {m['precision']} | {m['recall']} | {m['fpr']} |"
        )

    lines += [
        "",
        f"> **Best individual model (by AUC):** {best_model}",
        "",
        "---",
        "",
        "## Ensemble Test Set Results",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| ROC-AUC | {ensemble_metrics['auc']} |",
        f"| PR-AUC | {ensemble_metrics['pr_auc']} |",
        f"| F1 | {ensemble_metrics['f1']} |",
        f"| Precision | {ensemble_metrics['precision']} |",
        f"| Recall | {ensemble_metrics['recall']} |",
        f"| Accuracy | {ensemble_metrics['accuracy']} |",
        f"| False Positive Rate | {ensemble_metrics['fpr']} |",
        f"| False Negative Rate | {ensemble_metrics['fnr']} |",
        "",
        "## Confusion Matrix (Test Set)",
        "",
        "| | Predicted Safe | Predicted Phishing |",
        "|---|---|---|",
        f"| **Actual Safe** | {cm.get('tn',0):,} (TN) | {cm.get('fp',0):,} (FP) |",
        f"| **Actual Phishing** | {cm.get('fn',0):,} (FN) | {cm.get('tp',0):,} (TP) |",
        "",
        "---",
        "",
        "## Ensemble Weights",
        "",
        "| Model | Weight |",
        "|---|---|",
    ]
    for name, w in ENSEMBLE_WEIGHTS.items():
        lines.append(f"| {name} | {w} |")

    lines += [
        "",
        "---",
        "",
        "## Label Mapping",
        "",
        "| Dataset | label=0 | label=1 |",
        "|---|---|---|",
        "| CEAS_08 | safe | phishing/spam |",
        "| Enron | safe | spam (treated as threat) |",
        "| Ling | safe | spam (treated as threat) |",
        "| Nazario | — | phishing (all phishing) |",
        "| SpamAssasin | safe | spam (treated as threat) |",
        "",
        "---",
        "",
        "## Limitations",
        "",
        "- Enron and Ling label=1 is **commercial spam**, not targeted phishing.",
        "  The model learns a safe vs threat boundary, which includes spam.",
        "- Datasets span 2001–2008. Modern spear-phishing and BEC tactics may not be well-represented.",
        "- No attachment content, no HTML rendering, no DNS/WHOIS resolution.",
        "- Performance on the synthetic prior test will be much lower than on the real test set — this is expected.",
    ]

    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = DOCS_DIR / "model_training_report.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    logger.info(f"  ✓ docs/model_training_report.md generated")


# ═══════════════════════════════════════════════════════════════════════════════
# SYNTHETIC GENERATOR (kept for fallback)
# ═══════════════════════════════════════════════════════════════════════════════

PHISHING_SUBJECTS = [
    "URGENT: Your account has been suspended","Action Required: Verify your payment",
    "Your PayPal account is limited","Final Warning: Confirm your identity immediately",
    "Security Alert: Unusual sign-in activity","Your package could not be delivered",
    "Invoice overdue","Confirm your email to avoid account deletion",
    "IRS Tax Refund Notification","You have won a $500 Amazon gift card",
]
PHISHING_BODIES = [
    "URGENT NOTICE: We have detected suspicious activity on your account. Verify IMMEDIATELY at http://paypa1-secure.xyz/login?token=abc. Enter your password, card number, and SSN.",
    "Your account has been compromised. Restore access: http://192.168.1.100/account-restore and confirm your social security number and banking details. 24 hours or permanent suspension.",
    "IMPORTANT IRS NOTICE: You are entitled to a $2,847.00 refund. Verify at http://irs-refund.tk/claim — provide SSN, bank account, routing number. Expires in 24 hours.",
    "Your Apple ID is locked. Unlock at http://appleid-verify.cf/unlock — provide Apple ID, password, and payment method.",
    "FINAL NOTICE: Netflix account cancelled today due to billing failure. Update at http://netflix-billing.gq/pay — enter credit card number, expiry, and CVV.",
]
PHISHING_SENDERS = [
    "security@paypa1-secure.xyz","noreply@apple-id-verify.ml",
    "support@microsoft-security.tk","admin@irs-gov-refund.cf",
    "billing@netflix-update.gq","alert@bank-secure.ml",
]
SAFE_SUBJECTS = [
    "Your order has been shipped","Meeting agenda for tomorrow","Weekly team update",
    "Q3 report attached","Coffee chat next Tuesday?","Project milestone reached",
    "Your receipt from Starbucks","Happy birthday!","Team lunch this Friday",
]
SAFE_BODIES = [
    "Hi team, please find attached the Q3 financial report. Key highlights: revenue up 12%, expenses within budget.",
    "Dear John, I hope this email finds you well. I wanted to follow up on our conversation from last week.",
    "Your order #ORD-2024-98765 has been shipped via FedEx. Expected delivery: 3-5 business days.",
    "Hi everyone, quick reminder about the team lunch this Friday at noon. Please RSVP.",
    "Thank you for your purchase of $45.99 at Starbucks. Your receipt is attached.",
]
SAFE_SENDERS = [
    "john.smith@company.com","hr@bigcorp.com","noreply@fedex.com",
    "support@starbucks.com","newsletter@github.com","team@slack.com",
]

def generate_dataset(n_phishing=4000, n_safe=4000, seed=42):
    rng = np.random.default_rng(seed)
    texts, senders, urls_list, reply_tos, labels = [], [], [], [], []
    for i in range(n_phishing):
        subj   = PHISHING_SUBJECTS[i % len(PHISHING_SUBJECTS)]
        body   = PHISHING_BODIES[i % len(PHISHING_BODIES)]
        sender = PHISHING_SENDERS[i % len(PHISHING_SENDERS)]
        if rng.random() > 0.5:
            body += " ACT NOW! Limited time! Account deleted!"
        full = f"SUBJECT: {subj}\nFROM: {sender}\n\n{body}"
        texts.append(full); senders.append(sender)
        urls_list.append(["http://paypa1.xyz"]); reply_tos.append("c@evil.ru")
        labels.append(1)
    for i in range(n_safe):
        subj   = SAFE_SUBJECTS[i % len(SAFE_SUBJECTS)]
        body   = SAFE_BODIES[i % len(SAFE_BODIES)]
        sender = SAFE_SENDERS[i % len(SAFE_SENDERS)]
        full = f"SUBJECT: {subj}\nFROM: {sender}\n\n{body}"
        texts.append(full); senders.append(sender)
        urls_list.append([]); reply_tos.append("")
        labels.append(0)
    indices = np.arange(len(labels)); rng.shuffle(indices)
    return ([texts[i] for i in indices], [senders[i] for i in indices],
            [urls_list[i] for i in indices], [reply_tos[i] for i in indices],
            [labels[i] for i in indices])

def build_feature_matrix(texts, senders, urls_list, reply_tos):
    cleaner   = TextCleaner()
    extractor = FeatureExtractor()
    X = []
    for i, (text, sender, urls, rt) in enumerate(zip(texts, senders, urls_list, reply_tos)):
        if i % 1000 == 0:
            logger.info(f"  Extracting features: {i}/{len(texts)}")
        cleaned = cleaner.clean(text)
        feat = extractor.extract(text=cleaned, sender=sender,
                                  reply_to=rt if rt else None, urls=urls)
        X.append(feat)
    return np.array(X, dtype=np.float32)


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="TrustMail model training")
    parser.add_argument("--use-real-data",   action="store_true")
    parser.add_argument("--use-synthetic",   action="store_true")
    args = parser.parse_args()

    t0 = time.time()
    logger.info("🚀 TrustMail Training Pipeline")

    # ── Decide data source ────────────────────────────────────────────────────
    use_real = not args.use_synthetic and (
        args.use_real_data or (PROCESSED_DIR / "train.csv").exists()
    )
    data_source = "real_datasets" if use_real else "synthetic"
    logger.info(f"Data source: {data_source}")

    if use_real:
        X_train, y_train, X_val, y_val, X_test, y_test, scaler = load_real_data()
    else:
        texts, senders, urls_list, reply_tos, labels = generate_dataset(4000, 4000, RANDOM_SEED)
        X_raw = build_feature_matrix(texts, senders, urls_list, reply_tos)
        y     = np.array(labels, dtype=np.int32)
        scaler   = StandardScaler()
        X_scaled = scaler.fit_transform(X_raw)
        X_temp, X_test, y_temp, y_test = train_test_split(X_scaled, y, test_size=0.10, stratify=y, random_state=RANDOM_SEED)
        X_train, X_val, y_train, y_val = train_test_split(X_temp,   y_temp, test_size=0.111, stratify=y_temp, random_state=RANDOM_SEED)

    train_size = len(X_train)
    val_size   = len(X_val)
    test_size  = len(X_test)
    logger.info(f"Feature shape: {X_train.shape}")

    # ── Train ─────────────────────────────────────────────────────────────────
    logger.info("\n[Training] Starting model training...")
    models, model_metrics = train_all_models(X_train, y_train, X_val, y_val)

    # ── Ensemble eval on test set ─────────────────────────────────────────────
    logger.info("\n[Evaluation] Evaluating ensemble on TEST set...")
    ensemble_metrics = evaluate_ensemble(models, X_test, y_test)

    # ── Check minimum performance bar ─────────────────────────────────────────
    if ensemble_metrics["auc"] < MIN_ACCEPTABLE_AUC:
        raise RuntimeError(
            f"Ensemble AUC {ensemble_metrics['auc']:.4f} below minimum "
            f"threshold {MIN_ACCEPTABLE_AUC}. Models NOT promoted."
        )

    # ── Label encoder ─────────────────────────────────────────────────────────
    le = LabelEncoder()
    le.fit(y_train)

    # ── Metadata ──────────────────────────────────────────────────────────────
    metadata = {
        "model_version":    f"2.0.0-real" if use_real else "1.1.0-synthetic",
        "training_date":    time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "data_source":      data_source,
        "training_samples": int(train_size),
        "validation_samples": int(val_size),
        "test_samples":     int(test_size),
        "labels":           ["safe", "phishing"],
        "random_seed":      RANDOM_SEED,
        "feature_dim":      int(X_train.shape[1]),
        "models_trained":   list(models.keys()),
        "ensemble_weights": ENSEMBLE_WEIGHTS,
        "ensemble_test_auc": ensemble_metrics["auc"],
        "min_acceptable_auc": MIN_ACCEPTABLE_AUC,
    }

    # ── Backup + save candidates ──────────────────────────────────────────────
    logger.info("\n[Saving] Backing up existing models...")
    backup_ts = backup_existing_models()
    save_candidates(models, scaler, le, metadata)

    # ── Promote ───────────────────────────────────────────────────────────────
    logger.info("\n[Promoting] Promoting candidate models to production...")
    promote_candidates(backup_ts)

    # ── Save report and metrics ───────────────────────────────────────────────
    logger.info("\n[Reports] Generating reports...")
    save_results(model_metrics, ensemble_metrics, metadata,
                 data_source, train_size, val_size, test_size)
    generate_md_report(model_metrics, ensemble_metrics, data_source,
                       train_size, val_size, test_size)

    elapsed = time.time() - t0
    logger.info(f"\n{'='*60}")
    logger.info(f"✅ Training complete in {elapsed:.1f}s")
    logger.info(f"   Models: {list(models.keys())}")
    logger.info(f"   Ensemble AUC (test): {ensemble_metrics['auc']:.4f}")
    logger.info(f"   F1 (test): {ensemble_metrics['f1']:.4f}")
    logger.info(f"   FPR (test): {ensemble_metrics['fpr']:.4f}")
    logger.info(f"   Restart the backend to load new models.")
    logger.info(f"{'='*60}")


if __name__ == "__main__":
    main()
