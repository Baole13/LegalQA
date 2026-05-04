from __future__ import annotations

import re
import unicodedata
from typing import Iterable

TOKEN_PATTERN = re.compile(r"[a-z0-9]+", re.UNICODE)
ARTICLE_PATTERN = re.compile(r"(?:^|\n)\s*Điều\s+(\d+[A-Za-z]?)", re.IGNORECASE)
CLAUSE_PATTERN = re.compile(r"(?:^|\n)\s*(\d+[.)])")
STOPWORDS = {
    "ai",
    "bao",
    "bao_nhieu",
    "bi",
    "boi",
    "cho",
    "co",
    "cua",
    "da",
    "dang",
    "duoc",
    "gi",
    "khi",
    "la",
    "lam",
    "mot",
    "nao",
    "neu",
    "nguoi",
    "nhieu",
    "nhung",
    "roi",
    "se",
    "sao",
    "tai",
    "the",
    "theo",
    "thi",
    "tren",
    "tu",
    "va",
    "ve",
    "voi",
    "lao",
    "dong",
    "ngay",
    "nam",
}
SYNONYM_PHRASES = {
    "nghi phep": ["nghi hang nam", "nghi phep nam"],
    "phep nam": ["nghi hang nam", "nghi phep nam"],
    "bao hiem xa hoi": ["bhxh", "bao hiem"],
    "hop dong lao dong": ["hdld", "hop dong"],
    "don phuong cham dut": ["cham dut hop dong"],
}


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFC", text or "")
    text = text.replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def strip_accents(text: str) -> str:
    text = normalize_text(text)
    text = unicodedata.normalize("NFD", text)
    text = "".join(char for char in text if unicodedata.category(char) != "Mn")
    text = text.replace("đ", "d").replace("Đ", "D")
    return unicodedata.normalize("NFC", text)


def tokenize(text: str) -> list[str]:
    normalized = strip_accents(text).lower()
    return TOKEN_PATTERN.findall(normalized)


def keyword_text(text: str) -> str:
    return " ".join(tokenize(text))


def unique_preserve_order(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            output.append(value)
    return output


def detect_article(text: str) -> str | None:
    match = ARTICLE_PATTERN.search(text or "")
    return match.group(1) if match else None


def detect_clause(text: str) -> str | None:
    match = CLAUSE_PATTERN.search(text or "")
    if not match:
        return None
    return match.group(1).rstrip(".)")


def split_sentences(text: str) -> list[str]:
    text = (text or "").strip()
    if not text:
        return []
    parts = re.split(r"(?<=[.!?;:])\s+|\n+", text)
    return [normalize_text(part) for part in parts if normalize_text(part)]


def important_query_terms(text: str) -> list[str]:
    return [token for token in tokenize(text) if token not in STOPWORDS and len(token) > 2]


def important_query_phrases(text: str) -> list[str]:
    keywords = important_query_terms(text)
    if len(keywords) < 2:
        return []
    return [" ".join(keywords[index : index + 2]) for index in range(len(keywords) - 1)]


def expand_query(text: str) -> str:
    normalized = keyword_text(text)
    expansions = [normalized]
    for phrase, aliases in SYNONYM_PHRASES.items():
        if phrase in normalized:
            expansions.extend(aliases)
    return " ".join(unique_preserve_order(expansions))


def keyword_coverage_score(query: str, text: str) -> float:
    keywords = important_query_terms(query)
    if not keywords:
        return 0.0
    tokens = set(tokenize(text))
    hits = sum(1 for keyword in keywords if keyword in tokens)
    return hits / len(keywords)


def phrase_coverage_score(query: str, text: str) -> float:
    phrases = important_query_phrases(query)
    if not phrases:
        return 0.0
    normalized_text = keyword_text(text)
    hits = sum(1 for phrase in phrases if phrase in normalized_text)
    return hits / len(phrases)
