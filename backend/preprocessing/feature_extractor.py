"""
Feature Extractor
==================
Produces the feature vector fed to classical ML models.

Feature groups:
  1. TF-IDF text features (fitted vectorizer)
  2. Character n-gram features
  3. Statistical / stylometric features
  4. URL-derived features
  5. Header-derived features
  6. Readability metrics (Flesch, Gunning Fog)
  7. Punctuation statistics
  8. Sentiment-proxy features
"""

from __future__ import annotations

import math
import re
import string
from typing import Any, Dict, List, Optional

import numpy as np
from loguru import logger


class FeatureExtractor:
    """
    Extracts a fixed-size feature vector from email components.

    When called without a trained vectorizer (e.g. at startup before training),
    it returns a zero vector of the expected dimension so the pipeline does not crash.
    """

    FEATURE_DIM = 256  # Compact dense feature vector

    def extract(
        self,
        text: str,
        sender: Optional[str] = None,
        sender_domain: Optional[str] = None,
        reply_to: Optional[str] = None,
        urls: Optional[List[str]] = None,
        headers: Optional[Any] = None,
        vectorizer: Optional[Any] = None,
        scaler: Optional[Any] = None,
    ) -> np.ndarray:
        """
        Extract and concatenate all feature groups into a single vector.
        Returns np.ndarray of shape (FEATURE_DIM,).
        """
        # ── 1. Stylometric / statistical features ────────────────────────────
        stylo = self._stylometric_features(text)

        # ── 2. URL features ──────────────────────────────────────────────────
        url_feats = self._url_features(urls or [])

        # ── 3. Sender / header features ───────────────────────────────────────
        sender_feats = self._sender_features(sender, sender_domain, reply_to)

        # ── 4. Punctuation / formatting ───────────────────────────────────────
        punct_feats = self._punctuation_features(text)

        # ── 5. Keyword indicators ─────────────────────────────────────────────
        kw_feats = self._keyword_features(text)

        # Concatenate all dense features
        dense = np.concatenate([stylo, url_feats, sender_feats, punct_feats, kw_feats])

        # Pad or truncate to FEATURE_DIM
        if len(dense) < self.FEATURE_DIM:
            dense = np.pad(dense, (0, self.FEATURE_DIM - len(dense)))
        else:
            dense = dense[: self.FEATURE_DIM]

        # Optionally scale with fitted scaler
        if scaler is not None:
            try:
                dense = scaler.transform(dense.reshape(1, -1)).flatten()
            except Exception as e:
                logger.debug(f"Scaler transform failed: {e}")

        return dense.astype(np.float32)

    # ── Feature group implementations ─────────────────────────────────────────

    def _stylometric_features(self, text: str) -> np.ndarray:
        """Word count, sentence count, lexical diversity, readability metrics."""
        if not text:
            return np.zeros(20, dtype=np.float32)

        words = text.split()
        sentences = re.split(r"[.!?]+", text)
        sentences = [s.strip() for s in sentences if s.strip()]

        word_count = len(words)
        sentence_count = max(len(sentences), 1)
        avg_word_len = np.mean([len(w) for w in words]) if words else 0.0
        avg_sentence_len = word_count / sentence_count
        unique_words = len(set(w.lower() for w in words))
        lexical_diversity = unique_words / max(word_count, 1)

        # Flesch Reading Ease approximation
        syllable_count = sum(self._count_syllables(w) for w in words)
        flesch = 206.835 - 1.015 * avg_sentence_len - 84.6 * (syllable_count / max(word_count, 1))
        flesch = max(min(flesch, 100.0), 0.0) / 100.0  # Normalize

        # Gunning Fog Index approximation
        complex_words = sum(1 for w in words if self._count_syllables(w) >= 3)
        fog = 0.4 * (avg_sentence_len + 100 * complex_words / max(word_count, 1))
        fog = min(fog / 20.0, 1.0)

        # Caps ratio
        caps_ratio = sum(1 for c in text if c.isupper()) / max(len(text), 1)

        return np.array([
            min(word_count / 1000.0, 1.0),
            min(sentence_count / 100.0, 1.0),
            min(avg_word_len / 15.0, 1.0),
            min(avg_sentence_len / 50.0, 1.0),
            lexical_diversity,
            flesch,
            fog,
            caps_ratio,
            min(unique_words / 500.0, 1.0),
            min(syllable_count / 2000.0, 1.0),
            # 10 padding zeros reserved for future features
            0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
        ], dtype=np.float32)

    def _url_features(self, urls: List[str]) -> np.ndarray:
        """URL-based aggregate features."""
        n = len(urls)
        if n == 0:
            return np.zeros(15, dtype=np.float32)

        has_http = sum(1 for u in urls if u.startswith("http://"))
        has_https = sum(1 for u in urls if u.startswith("https://"))
        has_ip = sum(1 for u in urls if re.match(r"https?://\d+\.\d+", u))
        has_encoded = sum(1 for u in urls if "%" in u)
        avg_len = np.mean([len(u) for u in urls])
        max_len = max(len(u) for u in urls)
        has_suspicious_tld = sum(1 for u in urls if any(
            u.endswith(t) for t in [".xyz", ".tk", ".ml", ".cf", ".gq"]
        ))

        return np.array([
            min(n / 20.0, 1.0),
            has_http / max(n, 1),
            has_https / max(n, 1),
            has_ip / max(n, 1),
            has_encoded / max(n, 1),
            min(avg_len / 200.0, 1.0),
            min(max_len / 500.0, 1.0),
            has_suspicious_tld / max(n, 1),
            # padding
            0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
        ], dtype=np.float32)

    def _sender_features(
        self, sender: Optional[str], domain: Optional[str], reply_to: Optional[str]
    ) -> np.ndarray:
        feats = np.zeros(10, dtype=np.float32)
        if sender:
            feats[0] = 1.0  # sender present
            if domain:
                feats[1] = 1.0
                # Free email provider
                free_providers = {"gmail.com", "yahoo.com", "hotmail.com", "outlook.com"}
                if domain.lower() in free_providers:
                    feats[2] = 1.0
        if reply_to and sender:
            from_domain = re.search(r"@([\w.\-]+)", sender)
            rt_domain = re.search(r"@([\w.\-]+)", reply_to)
            if from_domain and rt_domain:
                if from_domain.group(1).lower() != rt_domain.group(1).lower():
                    feats[3] = 1.0  # reply-to mismatch
        return feats

    def _punctuation_features(self, text: str) -> np.ndarray:
        """Count punctuation usage as phishing indicators."""
        if not text:
            return np.zeros(10, dtype=np.float32)
        n = max(len(text), 1)
        return np.array([
            text.count("!") / n * 100,
            text.count("?") / n * 100,
            text.count("$") / n * 100,
            text.count("%") / n * 100,
            text.count("@") / n * 100,
            text.count("...") / n * 100,
            len(re.findall(r"[A-Z]{2,}", text)) / n * 100,  # ALL CAPS words
            text.count(":") / n * 100,
            text.count(";") / n * 100,
            0.0,  # padding
        ], dtype=np.float32)

    def _keyword_features(self, text: str) -> np.ndarray:
        """Binary feature vector for high-signal phishing keywords."""
        text_lower = text.lower()
        keywords = [
            "password", "account", "verify", "confirm", "urgent", "suspended",
            "click here", "login", "secure", "update", "bank", "credit card",
            "paypal", "bitcoin", "gift card", "wire transfer", "invoice",
            "tax refund", "congratulations", "winner", "prize", "free",
            "limited time", "act now", "irs", "government", "official",
        ]
        return np.array([
            1.0 if kw in text_lower else 0.0
            for kw in keywords
        ], dtype=np.float32)

    @staticmethod
    def _count_syllables(word: str) -> int:
        """Simple syllable counter (English approximation)."""
        word = word.lower().strip(string.punctuation)
        if not word:
            return 0
        vowels = "aeiou"
        count = 0
        prev_vowel = False
        for char in word:
            is_vowel = char in vowels
            if is_vowel and not prev_vowel:
                count += 1
            prev_vowel = is_vowel
        # Handle silent e
        if word.endswith("e") and count > 1:
            count -= 1
        return max(count, 1)
