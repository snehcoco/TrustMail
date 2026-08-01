"""
Model Loader — Classical Models Only
=====================================
Responsible for loading, caching, and providing access to:
  - Classical ML models (RF, XGBoost, LightGBM, CatBoost, LR)
  - Feature scaler (optional)
  - Label encoder (optional)

The ONNX/DistilBERT transformer has been intentionally removed.
All inference is CPU-only with no deep learning dependencies.

Uses eager loading: models are loaded once at startup and kept in memory.
Designed to be stored in app.state and shared across requests.
"""

from __future__ import annotations

import pickle
from pathlib import Path
from typing import Any, Dict, Optional

from loguru import logger

from config.settings import Settings


class ModelLoader:
    """
    Central model registry and loader — classical ensemble only.

    All models are loaded once at startup and cached.
    Thread-safe for read operations (single worker by default).
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        # Resolve MODELS_DIR relative to the backend/ directory so it works
        # regardless of whether the process is launched from backend/ or project root.
        _backend_dir = Path(__file__).parent.parent
        _models_dir  = Path(settings.MODELS_DIR)
        self.models_dir = (
            _models_dir if _models_dir.is_absolute()
            else _backend_dir / _models_dir
        )

        # Loaded model registry
        self._classical_models: Dict[str, Any] = {}
        self._scaler: Optional[Any] = None
        self._label_encoder: Optional[Any] = None
        self._is_ready: bool = False
        self._models_loaded: int = 0

    def load_all(self) -> None:
        """
        Load all classical models from disk.
        Failures are logged but do not crash the server —
        the API degrades gracefully to heuristic scoring.
        """
        self._load_classical_models()
        self._load_preprocessors()
        self._is_ready = True
        self._models_loaded = len(self._classical_models)

        if self._models_loaded > 0:
            logger.info(
                f"✅ ModelLoader ready — {self._models_loaded} classical models: "
                f"{list(self._classical_models.keys())}"
            )
        else:
            logger.warning(
                "⚠️  No trained models found — running in heuristic-only mode. "
                "Run: python training/run_training.py"
            )

    def _load_classical_models(self) -> None:
        ensemble_path = self.models_dir / self.settings.CLASSICAL_MODEL_FILE
        if not ensemble_path.exists():
            logger.warning(
                f"Classical ensemble not found at {ensemble_path}. "
                "Train models first: python training/run_training.py"
            )
            return
        try:
            with open(ensemble_path, "rb") as f:
                model_bundle = pickle.load(f)

            # Expected format: {"random_forest": model, "xgboost": model, ...}
            if isinstance(model_bundle, dict):
                self._classical_models = model_bundle
            else:
                # Legacy single-model format
                self._classical_models = {"ensemble": model_bundle}

            logger.info(f"✓ Classical models loaded: {list(self._classical_models.keys())}")
        except Exception as e:
            logger.error(f"Failed to load classical models: {e}")

    def _load_preprocessors(self) -> None:
        """Load optional scaler and label encoder."""
        for attr, filename in [
            ("_scaler", self.settings.SCALER_FILE),
            ("_label_encoder", self.settings.LABEL_ENCODER_FILE),
        ]:
            path = self.models_dir / filename
            if not path.exists():
                continue
            try:
                with open(path, "rb") as f:
                    setattr(self, attr, pickle.load(f))
                logger.info(f"✓ {filename} loaded")
            except Exception as e:
                logger.warning(f"Could not load {filename}: {e}")

    # ── Public accessors ──────────────────────────────────────────────────────

    def get_classical_model(self, name: str) -> Optional[Any]:
        """Return a loaded classical model by key, or None if not available."""
        return self._classical_models.get(name)

    def get_scaler(self) -> Optional[Any]:
        return self._scaler

    def is_ready(self) -> bool:
        return self._is_ready

    def has_trained_models(self) -> bool:
        return self._models_loaded > 0

    def get_model_version(self) -> str:
        return self.settings.API_VERSION

    def get_loaded_models(self) -> Dict[str, bool]:
        return {
            "random_forest":       "random_forest" in self._classical_models,
            "xgboost":             "xgboost" in self._classical_models,
            "lightgbm":            "lightgbm" in self._classical_models,
            "catboost":            "catboost" in self._classical_models,
            "logistic_regression": "logistic_regression" in self._classical_models,
            "scaler":              self._scaler is not None,
        }

    def get_model_versions(self) -> Dict[str, str]:
        return {k: self.settings.API_VERSION for k in self.get_loaded_models()}

    def unload_all(self) -> None:
        """Release models from memory on server shutdown."""
        self._classical_models.clear()
        self._scaler = None
        self._is_ready = False
        self._models_loaded = 0
        logger.info("All models unloaded.")
