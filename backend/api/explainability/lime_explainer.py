"""
LIME Explainer
==============
Generates LIME (Local Interpretable Model-agnostic Explanations).

LIME perturbs the input text and observes how the model's prediction changes,
fitting a locally linear model to explain the specific prediction.

Unlike SHAP, LIME works directly on raw text, making it especially useful
for explaining transformer model predictions.
"""

from __future__ import annotations

from typing import Callable, List, Optional

import numpy as np
from loguru import logger

from api.schemas.response_schemas import FeatureImportanceItem, LIMEExplanation


class LIMEExplainer:
    """
    LIME text explainer for phishing classification.

    Uses LimeTextExplainer from the lime library.
    Falls back gracefully if lime is not installed.
    """

    def __init__(self, model_loader) -> None:
        self.model_loader = model_loader

    def explain(
        self,
        text: str,
        features: np.ndarray,
        num_features: int = 15,
        num_samples: int = 300,
    ) -> Optional[LIMEExplanation]:
        """
        Generate LIME explanation for the given text.

        Args:
            text: Cleaned email text (used for perturbation).
            features: Pre-computed feature vector (used as fallback).
            num_features: Number of features to include in explanation.
            num_samples: Number of perturbed samples.

        Returns:
            LIMEExplanation or None if LIME fails.
        """
        try:
            from lime.lime_text import LimeTextExplainer

            explainer = LimeTextExplainer(
                class_names=["safe", "phishing"],
                char_level=False,
            )

            # Build predict function using ONNX runner if available
            predict_fn = self._build_predict_fn()
            if predict_fn is None:
                logger.debug("No model available for LIME")
                return self._mock_explanation(text, num_features)

            exp = explainer.explain_instance(
                text,
                predict_fn,
                num_features=num_features,
                num_samples=num_samples,
                labels=[1],  # Explain phishing class
            )

            lime_list = exp.as_list(label=1)
            items = [
                FeatureImportanceItem(
                    feature=word,
                    importance=round(float(weight), 5),
                    direction="phishing" if weight > 0 else "safe",
                )
                for word, weight in lime_list
            ]

            local_pred = exp.local_pred[0] if exp.local_pred else 0.5

            return LIMEExplanation(
                top_features=items,
                intercept=round(float(exp.intercept[1]), 5),
                local_prediction=round(float(local_pred), 5),
                score=round(float(exp.score), 5),
            )

        except ImportError:
            logger.warning("LIME not installed. Install with: pip install lime")
            return None
        except Exception as e:
            logger.warning(f"LIME explanation failed: {e}")
            return None

    def _build_predict_fn(self) -> Optional[Callable]:
        """
        Returns a predict function suitable for LIME perturbation.
        LIME calls this with a list of text strings and expects
        a [n_samples, n_classes] probability array back.
        Uses the best available classical model.
        """
        for name in ["random_forest", "xgboost", "lightgbm", "catboost", "logistic_regression"]:
            try:
                from preprocessing.feature_extractor import FeatureExtractor
                from preprocessing.text_cleaner import TextCleaner
                model = self.model_loader.get_classical_model(name)
                if model is None:
                    continue

                cleaner = TextCleaner()
                extractor = FeatureExtractor()

                def predict_classical(texts: List[str]) -> np.ndarray:
                    results = []
                    for t in texts:
                        cleaned = cleaner.clean(t)
                        feats = extractor.extract(text=cleaned)
                        prob = float(model.predict_proba(feats.reshape(1, -1))[0, 1])
                        results.append([1 - prob, prob])
                    return np.array(results)

                logger.debug(f"LIME predict_fn: using {name}")
                return predict_classical
            except Exception:
                continue

        return None


    def _mock_explanation(self, text: str, num_features: int) -> LIMEExplanation:
        """Placeholder explanation for development."""
        words = list(set(text.split()))[:num_features]
        items = [
            FeatureImportanceItem(
                feature=w,
                importance=round(np.random.uniform(-0.1, 0.1), 5),
                direction="phishing",
            )
            for w in words
        ]
        return LIMEExplanation(
            top_features=items,
            intercept=0.5,
            local_prediction=0.5,
            score=0.0,
        )
