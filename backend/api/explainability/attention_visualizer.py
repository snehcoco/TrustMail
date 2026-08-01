"""
Attention Visualizer
====================
Extracts token-level attention weights from the DistilBERT ONNX model.

Note: Standard ONNX exports don't include attention weights by default.
The training script (train_transformer.py) must export with attention
outputs enabled for this module to produce meaningful results.

This provides word-level heatmap data for the extension's UI.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np
from loguru import logger

from api.schemas.request_schemas import AnalyzeRequest
from preprocessing.text_cleaner import TextCleaner


class AttentionVisualizer:
    """
    Extracts and formats attention weights from the transformer model.

    Returns a list of {token, attention_weight} dicts suitable
    for rendering as a heatmap in the frontend.
    """

    def __init__(self, model_loader) -> None:
        self.model_loader = model_loader
        self.text_cleaner = TextCleaner()

    def get_highlights(self, request: AnalyzeRequest) -> Optional[List[Dict[str, Any]]]:
        """
        Extract attention highlights from the email text.
        Returns None if attention weights are not available.
        """
        try:
            onnx_runner = self.model_loader.get_onnx_runner()

            # Check if the model exports attention weights
            output_names = [o.name for o in onnx_runner._session.get_outputs()]
            has_attention = any("attention" in n.lower() for n in output_names)

            if not has_attention:
                logger.debug("ONNX model does not export attention weights")
                return None

            text = self._build_text(request)
            clean_text = self.text_cleaner.clean(text)

            # Get tokenized input
            tokenized = onnx_runner._tokenize(clean_text)

            # Run inference with all outputs
            outputs = onnx_runner._session.run(None, tokenized)

            # Find attention output (shape: [batch, heads, seq, seq])
            attn_output = None
            for name, output in zip(output_names, outputs):
                if "attention" in name.lower():
                    attn_output = output
                    break

            if attn_output is None:
                return None

            # Average over all attention heads and layers, focus on CLS token
            # Shape: [batch, heads, seq_len, seq_len]
            avg_attention = attn_output[0].mean(axis=0)[0]  # [seq_len]

            # Get tokens
            tokens = self._get_tokens(onnx_runner, clean_text)

            highlights = []
            for i, (token, attn_weight) in enumerate(zip(tokens[:50], avg_attention[:50])):
                if token not in ("[CLS]", "[SEP]", "[PAD]", "<s>", "</s>"):
                    highlights.append({
                        "token": token,
                        "attention": round(float(attn_weight), 5),
                        "position": i,
                    })

            return highlights

        except Exception as e:
            logger.debug(f"Attention visualization failed: {e}")
            return None

    def _build_text(self, request: AnalyzeRequest) -> str:
        parts = []
        if request.subject:
            parts.append(request.subject)
        if request.body_text:
            parts.append(request.body_text[:2000])
        return " ".join(parts)

    def _get_tokens(self, onnx_runner, text: str) -> List[str]:
        """Try to decode input_ids back to token strings."""
        try:
            tokenizer = onnx_runner._tokenizer
            if tokenizer and hasattr(tokenizer, "convert_ids_to_tokens"):
                tokenized = onnx_runner._tokenize(text)
                ids = tokenized["input_ids"][0].tolist()
                return tokenizer.convert_ids_to_tokens(ids)
        except Exception:
            pass
        return [f"tok_{i}" for i in range(512)]
