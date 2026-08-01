"""
TrustMail — Classical Ensemble Service
=======================================
Combines predictions from 5 classical ML models:
  - Random Forest
  - XGBoost
  - LightGBM
  - CatBoost
  - Logistic Regression

Uses weighted averaging with calibrated probabilities.
The ONNX/DistilBERT stage has been intentionally removed.
All inference is CPU-only with no deep learning dependencies.

Falls back gracefully to heuristic scoring when models are not yet trained.
"""

from __future__ import annotations

from typing import List, Tuple

import numpy as np
from loguru import logger

from api.schemas.response_schemas import ModelPrediction

# Ensemble weights — must sum to 1.0
# Adjust in config/model_config.yaml; these are the runtime defaults.
DEFAULT_WEIGHTS = {
    "random_forest":      0.30,
    "xgboost":            0.28,
    "lightgbm":           0.22,
    "catboost":           0.12,
    "logistic_regression": 0.08,
}


class EnsembleService:
    """
    Classical model ensemble coordinator.

    Accepts a ModelLoader (injected from app.state) and uses
    whatever models are available, adjusting weights proportionally
    when some models are unavailable.
    """

    def __init__(self, model_loader) -> None:
        self.model_loader = model_loader
        self._weights = DEFAULT_WEIGHTS.copy()

    def predict(
        self, features: np.ndarray, text: str
    ) -> Tuple[float, float, List[ModelPrediction]]:
        """
        Run all available classical models and return:
          (ensemble_phishing_probability, confidence, per_model_predictions)

        confidence is computed as distance from the decision boundary (0.5):
            confidence = |prob - 0.5| * 2   →  [0.0, 1.0]

        When no models are loaded (heuristic fallback), returns
        (0.0, 0.0, []) so the caller can use rule-based scores instead.
        """
        predictions: List[ModelPrediction] = []
        weighted_sum = 0.0
        total_weight = 0.0

        classical_models = {
            "random_forest":       "Random Forest",
            "xgboost":             "XGBoost",
            "lightgbm":            "LightGBM",
            "catboost":            "CatBoost",
            "logistic_regression": "Logistic Regression",
        }

        for key, display_name in classical_models.items():
            try:
                model = self.model_loader.get_classical_model(key)
                if model is None:
                    continue

                prob = float(model.predict_proba(features.reshape(1, -1))[0, 1])
                weight = self._weights.get(key, 0.1)

                predictions.append(ModelPrediction(
                    model_name=display_name,
                    phishing_probability=round(prob, 4),
                    weight=weight,
                    weighted_contribution=round(prob * weight, 4),
                ))
                weighted_sum += prob * weight
                total_weight += weight

            except Exception as e:
                logger.debug(f"Model {key} unavailable: {e}")

        # No models loaded — caller will use heuristic scoring
        if total_weight == 0:
            logger.warning("No classical models available — using heuristic fallback")
            return 0.0, 0.0, []

        # Normalize by actual available weight (handles missing models gracefully)
        ensemble_prob = weighted_sum / total_weight

        # Confidence = how far the prediction is from 0.5 (the decision boundary)
        # A score of 0.95 → confidence = |0.95 - 0.5| * 2 = 0.90 (very confident)
        # A score of 0.52 → confidence = |0.52 - 0.5| * 2 = 0.04 (uncertain)
        confidence = abs(ensemble_prob - 0.5) * 2.0

        return round(ensemble_prob, 4), round(confidence, 4), predictions
