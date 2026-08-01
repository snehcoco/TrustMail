"""
Text Cleaner
=============
Normalizes email text for NLP processing:
  - HTML tag removal
  - URL normalization
  - Whitespace normalization
  - Unicode normalization
  - Header artifact removal
  - Encoding cleanup
"""

from __future__ import annotations

import re
import unicodedata


class TextCleaner:
    """
    Stateless text normalization pipeline.

    Produces clean, consistent text for both TF-IDF vectorization
    and transformer tokenization.
    """

    # Patterns compiled once for efficiency
    _HTML_TAGS = re.compile(r"<[^>]+>", re.DOTALL)
    _URL_PATTERN = re.compile(r"https?://[^\s]+|www\.[^\s]+", re.IGNORECASE)
    _EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Z|a-z]{2,}\b")
    _WHITESPACE = re.compile(r"\s+")
    _REPEATED_PUNCT = re.compile(r"([!?.]){3,}")
    _NON_ASCII_CTRL = re.compile(r"[\x00-\x08\x0b-\x0c\x0e-\x1f\x7f-\x9f]")

    def clean(self, text: str, preserve_urls: bool = False) -> str:
        """
        Full cleaning pipeline.

        Args:
            text: Raw email text (may contain HTML).
            preserve_urls: If True, replace URLs with __URL__ token instead of removing.
        """
        if not text:
            return ""

        # 1. Unicode normalization (handle encoding issues, smart quotes, etc.)
        text = unicodedata.normalize("NFKC", text)

        # 2. Remove control characters
        text = self._NON_ASCII_CTRL.sub(" ", text)

        # 3. Strip HTML
        text = self._HTML_TAGS.sub(" ", text)

        # 4. Handle URLs
        if preserve_urls:
            text = self._URL_PATTERN.sub(" __URL__ ", text)
        else:
            text = self._URL_PATTERN.sub(" ", text)

        # 5. Normalize email addresses to token
        text = self._EMAIL_PATTERN.sub(" __EMAIL__ ", text)

        # 6. Normalize repeated punctuation
        text = self._REPEATED_PUNCT.sub(r"\1\1", text)

        # 7. Collapse whitespace
        text = self._WHITESPACE.sub(" ", text)

        return text.strip()

    def clean_subject(self, subject: str) -> str:
        """Clean email subject line (more conservative)."""
        subject = re.sub(r"^\s*(Re|Fwd|FW|RE):\s*", "", subject, flags=re.IGNORECASE)
        return self.clean(subject)

    def extract_text_from_html(self, html: str) -> str:
        """Extract readable text from HTML, preserving link anchor text."""
        # Replace <br> and <p> with newlines before stripping all tags
        html = re.sub(r"<br\s*/?>|</p>|</div>|</li>", "\n", html, flags=re.IGNORECASE)
        text = self._HTML_TAGS.sub(" ", html)
        text = self._WHITESPACE.sub(" ", text)
        return text.strip()
