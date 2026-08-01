"""
SHAP Explainer
==============
Generates SHAP (SHapley Additive exPlanations) values for model predictions.

SHAP provides mathematically grounded feature importance explanations that
show each feature's contribution to moving the prediction from the base rate
toward the final phishing probability.

Uses TreeExplainer for classical models (fast, exact) and
KernelExplainer fallback for any model type (slower, approximate).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np
from loguru import logger

from api.schemas.response_schemas import FeatureImportanceItem, SHAPExplanation

# Feature names corresponding to the 256-dim feature vector
# (should match FeatureExtractor output order)
FEATURE_NAMES = [
    # Stylometric (indices 0–19)
    "word_count", "sentence_count", "avg_word_length", "avg_sentence_length",
    "lexical_diversity", "flesch_readability", "gunning_fog", "caps_ratio",
    "unique_words", "syllable_count",
    "stylo_pad_10", "stylo_pad_11", "stylo_pad_12", "stylo_pad_13", "stylo_pad_14",
    "stylo_pad_15", "stylo_pad_16", "stylo_pad_17", "stylo_pad_18", "stylo_pad_19",
    # URL features (indices 20–34)
    "url_count", "http_url_ratio", "https_url_ratio", "ip_url_ratio",
    "encoded_url_ratio", "avg_url_length", "max_url_length", "suspicious_tld_ratio",
    "url_pad_8", "url_pad_9", "url_pad_10", "url_pad_11", "url_pad_12",
    "url_pad_13", "url_pad_14",
    # Sender features (indices 35–44)
    "sender_present", "sender_domain_present", "free_email_provider",
    "reply_to_mismatch", "sender_pad_4", "sender_pad_5", "sender_pad_6",
    "sender_pad_7", "sender_pad_8", "sender_pad_9",
    # Punctuation features (indices 45–54)
    "exclamation_ratio", "question_ratio", "dollar_ratio", "percent_ratio",
    "at_ratio", "ellipsis_ratio", "caps_word_ratio", "colon_ratio",
    "semicolon_ratio", "punct_pad_9",
    # Keyword features (indices 55–80)
    "kw_password", "kw_account", "kw_verify", "kw_confirm", "kw_urgent",
    "kw_suspended", "kw_click_here", "kw_login", "kw_secure", "kw_update",
    "kw_bank", "kw_credit_card", "kw_paypal", "kw_bitcoin", "kw_gift_card",
    "kw_wire_transfer", "kw_invoice", "kw_tax_refund", "kw_congratulations",
    "kw_winner", "kw_prize", "kw_free", "kw_limited_time", "kw_act_now",
    "kw_irs", "kw_government",
]

# Pad to 256
FEATURE_NAMES = FEATURE_NAMES + [f"feat_{i}" for i in range(256 - len(FEATURE_NAMES))]


class SHAPExplainer:
    """
    SHAP-based explanation generator.

    Prefers TreeExplainer (for RF/XGB/LGB/CatBoost) for speed.
    Falls back to KernelExplainer for other model types.
    """

    def __init__(self, model_loader) -> None:
        self.model_loader = model_loader

    def explain(
        self, features: np.ndarray, max_features: int = 20
    ) -> Optional[SHAPExplanation]:
        """
        Generate SHAP explanation for the given feature vector.

        Returns None if SHAP is unavailable or fails.
        """
        try:
            import shap

            # Prefer Random Forest as it has the fastest SHAP computation
            model = (
                self.model_loader.get_classical_model("random_forest")
                or self.model_loader.get_classical_model("xgboost")
                or self.model_loader.get_classical_model("lightgbm")
            )

            if model is None:
                logger.debug("No classical model available for SHAP")
                return self._mock_explanation(features, max_features)

            features_2d = features.reshape(1, -1)

            # Try TreeExplainer first (fast, exact)
            try:
                explainer = shap.TreeExplainer(model)
                shap_values = explainer.shap_values(features_2d)

                # Handle different SHAP return shapes across library versions:
                # - Old: list of 2 arrays [neg_class, pos_class]
                # - New: single 3D array (1, n_features, n_classes) or 2D (1, n_features)
                ev = explainer.expected_value
                if isinstance(shap_values, list):
                    # Old SHAP: list of [neg_class_values, pos_class_values]
                    sv = shap_values[1][0] if len(shap_values) > 1 else shap_values[0][0]
                    base_value = float(ev[1]) if hasattr(ev, "__len__") and len(ev) > 1 else float(ev)
                elif isinstance(shap_values, np.ndarray) and shap_values.ndim == 3:
                    # New SHAP: shape (1, n_features, n_classes)
                    sv = shap_values[0, :, 1]
                    base_value = float(ev[1]) if hasattr(ev, "__len__") and len(ev) > 1 else float(ev)
                else:
                    # 2D: shape (1, n_features)
                    sv = shap_values[0]
                    base_value = float(ev[0]) if hasattr(ev, "__len__") and len(ev) > 0 else float(ev)

            except Exception:
                # KernelExplainer fallback
                def predict_fn(x):
                    return model.predict_proba(x)[:, 1]

                background = shap.kmeans(features_2d, 1)
                explainer = shap.KernelExplainer(predict_fn, background)
                sv = explainer.shap_values(features_2d, nsamples=50)[0]
                base_value = float(explainer.expected_value)

            return self._build_explanation(sv, base_value, max_features)

        except ImportError:
            logger.warning("SHAP not installed. Install with: pip install shap")
            return None
        except Exception as e:
            logger.warning(f"SHAP explanation failed: {e}")
            return None

    def _build_explanation(
        self, shap_values: np.ndarray, base_value: float, max_features: int
    ) -> SHAPExplanation:
        """Build SHAPExplanation from raw shap values."""
        indices = np.argsort(np.abs(shap_values))[::-1][:max_features]

        items = []
        for idx in indices:
            val = float(shap_values[idx])
            name = FEATURE_NAMES[idx] if idx < len(FEATURE_NAMES) else f"feature_{idx}"
            items.append(FeatureImportanceItem(
                feature=name,
                importance=round(val, 5),
                direction="phishing" if val > 0 else "safe",
            ))

        expected_value = base_value + float(np.sum(shap_values))

        return SHAPExplanation(
            top_features=items,
            base_value=round(base_value, 5),
            expected_value=round(expected_value, 5),
            shap_values_summary={
                FEATURE_NAMES[i]: round(float(shap_values[i]), 5)
                for i in indices
            },
        )

    def _mock_explanation(self, features: np.ndarray, max_features: int) -> SHAPExplanation:
        """
        Returns a placeholder explanation when no model is available.
        Used during development before training completes.
        """
        items = [
            FeatureImportanceItem(
                feature=FEATURE_NAMES[i] if i < len(FEATURE_NAMES) else f"feature_{i}",
                importance=round(float(features[i]) * 0.1, 5),
                direction="phishing" if features[i] > 0 else "safe",
            )
            for i in range(min(max_features, len(features)))
        ]
        return SHAPExplanation(
            top_features=items,
            base_value=0.5,
            expected_value=float(np.mean(features[:max_features]) * 0.5 + 0.5),
        )
