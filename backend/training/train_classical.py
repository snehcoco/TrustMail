"""
Classical Model Training Pipeline
====================================
Trains the classical ML ensemble:
  - Logistic Regression
  - Random Forest
  - XGBoost
  - LightGBM
  - CatBoost
  - Support Vector Machine

Produces a pickled bundle of all models + vectorizer + scaler.
Run this BEFORE training the transformer.

Usage:
    cd backend
    python training/train_classical.py

Output:
    trained_models/ensemble_classical.pkl
    trained_models/tfidf_vectorizer.pkl
    trained_models/feature_scaler.pkl
    trained_models/label_encoder.pkl
"""

import argparse
import os
import pickle
import sys
from pathlib import Path

import mlflow
import numpy as np
from loguru import logger
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report, roc_auc_score
from sklearn.model_selection import StratifiedKFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import LabelEncoder, StandardScaler
from sklearn.svm import LinearSVC

sys.path.insert(0, str(Path(__file__).parent.parent))

from preprocessing.feature_extractor import FeatureExtractor
from preprocessing.text_cleaner import TextCleaner
from config.settings import get_settings

settings = get_settings()


def load_training_data(data_dir: Path):
    """Load processed training data from disk."""
    import pandas as pd

    train_path = data_dir / "train.csv"
    if not train_path.exists():
        raise FileNotFoundError(
            f"Training data not found at {train_path}. "
            "Run: python datasets/download_datasets.py && python datasets/preprocess_datasets.py"
        )

    df = pd.read_csv(train_path)
    logger.info(f"Loaded {len(df)} training examples")
    logger.info(f"Label distribution:\n{df['label'].value_counts()}")
    return df


def extract_features(df, cleaner: TextCleaner, extractor: FeatureExtractor) -> tuple:
    """Extract feature matrix and labels from DataFrame."""
    texts = []
    features = []
    labels = []

    for _, row in df.iterrows():
        text = str(row.get("text", "")) + " " + str(row.get("subject", ""))
        cleaned = cleaner.clean(text)
        feat = extractor.extract(
            text=cleaned,
            sender=str(row.get("sender", "")),
            sender_domain=str(row.get("sender_domain", "")),
        )
        texts.append(cleaned)
        features.append(feat)
        labels.append(int(row.get("label", 0)))

    X = np.array(features, dtype=np.float32)
    y = np.array(labels, dtype=np.int32)
    return X, y, texts


def train_models(X_train, y_train, X_val, y_val) -> dict:
    """Train all classical models and return a model bundle dict."""
    from sklearn.feature_extraction.text import TfidfVectorizer

    models_trained = {}

    # ── Logistic Regression ──────────────────────────────────────────────────
    logger.info("Training Logistic Regression...")
    lr = LogisticRegression(
        C=1.0, max_iter=1000, class_weight="balanced", random_state=42
    )
    lr.fit(X_train, y_train)
    models_trained["logistic_regression"] = lr
    _log_model_metrics("logistic_regression", lr, X_val, y_val)

    # ── Random Forest ─────────────────────────────────────────────────────────
    logger.info("Training Random Forest...")
    rf = RandomForestClassifier(
        n_estimators=200,
        max_depth=20,
        min_samples_split=5,
        class_weight="balanced",
        n_jobs=-1,
        random_state=42,
    )
    rf.fit(X_train, y_train)
    models_trained["random_forest"] = rf
    _log_model_metrics("random_forest", rf, X_val, y_val)

    # ── XGBoost ───────────────────────────────────────────────────────────────
    try:
        from xgboost import XGBClassifier
        logger.info("Training XGBoost...")
        xgb = XGBClassifier(
            n_estimators=300,
            max_depth=6,
            learning_rate=0.1,
            subsample=0.8,
            colsample_bytree=0.8,
            use_label_encoder=False,
            eval_metric="logloss",
            n_jobs=-1,
            random_state=42,
        )
        xgb.fit(X_train, y_train)
        models_trained["xgboost"] = xgb
        _log_model_metrics("xgboost", xgb, X_val, y_val)
    except ImportError:
        logger.warning("XGBoost not installed, skipping")

    # ── LightGBM ──────────────────────────────────────────────────────────────
    try:
        import lightgbm as lgb
        logger.info("Training LightGBM...")
        lgbm = lgb.LGBMClassifier(
            n_estimators=300,
            max_depth=8,
            learning_rate=0.05,
            subsample=0.8,
            colsample_bytree=0.8,
            class_weight="balanced",
            n_jobs=-1,
            random_state=42,
            verbose=-1,
        )
        lgbm.fit(X_train, y_train)
        models_trained["lightgbm"] = lgbm
        _log_model_metrics("lightgbm", lgbm, X_val, y_val)
    except ImportError:
        logger.warning("LightGBM not installed, skipping")

    # ── CatBoost ──────────────────────────────────────────────────────────────
    try:
        from catboost import CatBoostClassifier
        logger.info("Training CatBoost...")
        cat = CatBoostClassifier(
            iterations=300,
            depth=8,
            learning_rate=0.05,
            loss_function="Logloss",
            auto_class_weights="Balanced",
            random_seed=42,
            verbose=False,
        )
        cat.fit(X_train, y_train)
        models_trained["catboost"] = cat
        _log_model_metrics("catboost", cat, X_val, y_val)
    except ImportError:
        logger.warning("CatBoost not installed, skipping")

    # ── SVM (LinearSVC + Calibration) ─────────────────────────────────────────
    logger.info("Training SVM...")
    svm = CalibratedClassifierCV(
        LinearSVC(class_weight="balanced", max_iter=2000, random_state=42),
        cv=3,
    )
    svm.fit(X_train, y_train)
    models_trained["svm"] = svm
    _log_model_metrics("svm", svm, X_val, y_val)

    return models_trained


def _log_model_metrics(name: str, model, X_val, y_val) -> None:
    """Log classification metrics for a model."""
    preds = model.predict(X_val)
    proba = model.predict_proba(X_val)[:, 1]
    auc = roc_auc_score(y_val, proba)
    report = classification_report(y_val, preds, target_names=["safe", "phishing"])
    logger.info(f"\n[{name}] AUC={auc:.4f}\n{report}")
    mlflow.log_metric(f"{name}_auc", auc)


def save_models(models: dict, output_dir: Path) -> None:
    """Serialize all models to disk."""
    output_dir.mkdir(parents=True, exist_ok=True)

    model_path = output_dir / settings.CLASSICAL_MODEL_FILE
    with open(model_path, "wb") as f:
        pickle.dump(models, f, protocol=pickle.HIGHEST_PROTOCOL)
    logger.info(f"✓ Classical model bundle saved: {model_path}")


def main():
    parser = argparse.ArgumentParser(description="Train TrustMail classical models")
    parser.add_argument("--data-dir", default="datasets/processed", help="Processed data directory")
    parser.add_argument("--output-dir", default=settings.MODELS_DIR, help="Model output directory")
    parser.add_argument("--experiment", default=settings.MLFLOW_EXPERIMENT_NAME)
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    output_dir = Path(args.output_dir)

    mlflow.set_tracking_uri(settings.MLFLOW_TRACKING_URI)
    mlflow.set_experiment(args.experiment)

    with mlflow.start_run(run_name="classical_ensemble_training"):
        cleaner = TextCleaner()
        extractor = FeatureExtractor()

        logger.info("Loading training data...")
        train_df = load_training_data(data_dir)
        val_path = data_dir / "val.csv"
        import pandas as pd
        val_df = pd.read_csv(val_path) if val_path.exists() else train_df.sample(frac=0.2, random_state=42)

        logger.info("Extracting features...")
        X_train, y_train, _ = extract_features(train_df, cleaner, extractor)
        X_val, y_val, _ = extract_features(val_df, cleaner, extractor)

        mlflow.log_params({
            "n_train": len(X_train),
            "n_val": len(X_val),
            "feature_dim": X_train.shape[1],
        })

        logger.info("Training models...")
        models = train_models(X_train, y_train, X_val, y_val)

        logger.info("Saving models...")
        save_models(models, output_dir)

        logger.info("✅ Classical model training complete!")


if __name__ == "__main__":
    main()
