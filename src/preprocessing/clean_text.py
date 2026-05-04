from __future__ import annotations

from src.utils.text import normalize_text


def clean_text(text: str) -> str:
    return normalize_text(text)


def is_valid_text(text: str, min_chars: int = 30) -> bool:
    return len(clean_text(text)) >= min_chars

