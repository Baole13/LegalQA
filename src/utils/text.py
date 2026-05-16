from __future__ import annotations

import re
import unicodedata
from typing import Iterable

TOKEN_PATTERN = re.compile(r"[a-z0-9]+", re.UNICODE)
ARTICLE_PATTERN = re.compile(r"(?:^|\n)\s*Điều\s+(\d+[A-Za-z]?)", re.IGNORECASE)
CLAUSE_PATTERN = re.compile(r"(?:^|\n)\s*(\d+)[.)]")
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
}
SYNONYM_PHRASES = {
    "nghi phep": ["nghi hang nam", "nghi phep nam"],
    "phep nam": ["nghi hang nam", "nghi phep nam"],
    "bao hiem xa hoi": ["bhxh", "bao hiem"],
    "hop dong lao dong": ["hdld", "hop dong"],
    "don phuong cham dut": ["cham dut hop dong"],
}
PROCEDURAL_NOISE_PHRASES = {
    "bao cao",
    "don xin",
    "ho so",
    "quy trinh",
    "thu tuc",
    "thanh toan",
    "thu truong",
    "giai quyet",
    "om dau",
    "tro cap",
}
QUANTITY_ANSWER_PHRASES = {
    "bao nhieu",
    "so ngay",
    "muc huong",
    "thoi han",
    "toi da",
    "it nhat",
    "khong qua",
    "duoc nghi",
    "duoc huong",
}
AUTHORITY_ANSWER_PHRASES = {
    "co tham quyen",
    "ra quyet dinh",
    "giam doc",
    "bo truong",
    "chu tich",
    "uy ban",
    "co quan",
    "nguoi dung dau",
}
YES_NO_ANSWER_PHRASES = {
    "co trach nhiem",
    "khong co trach nhiem",
    "phai",
    "khong phai",
    "duoc",
    "khong duoc",
    "bat buoc",
}
LEGAL_TITLE_HINTS = (
    "bo luat",
    "luat",
    "nghi dinh",
    "thong tu",
    "nghi quyet",
    "quyet dinh",
    "phap lenh",
    "thoa thuan quoc te",
)


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFC", text or "")
    text = text.replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def strip_accents(text: str) -> str:
    text = normalize_text(text)
    text = text.replace("đ", "d").replace("Đ", "D")
    text = unicodedata.normalize("NFD", text)
    text = "".join(char for char in text if unicodedata.category(char) != "Mn")
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
    return match.group(1)


def split_sentences(text: str) -> list[str]:
    text = (text or "").strip()
    if not text:
        return []
    parts = re.split(r"(?<=[.!?;:])\s+|\n+", text)
    return [normalize_text(part) for part in parts if normalize_text(part)]


def normalized_text(text: str) -> str:
    return keyword_text(text)


def important_query_terms(text: str) -> list[str]:
    return [token for token in tokenize(text) if token not in STOPWORDS and len(token) > 2]


def important_query_phrases(text: str) -> list[str]:
    keywords = important_query_terms(text)
    if len(keywords) < 2:
        return []
    return [" ".join(keywords[index : index + 2]) for index in range(len(keywords) - 1)]


def detect_question_intent(text: str) -> str:
    normalized = normalized_text(text)
    if any(phrase in normalized for phrase in ("bao nhieu", "bao lau", "may", "thoi han", "muc huong")):
        return "quantity"
    if normalized.startswith("ai ") or " ai " in f" {normalized} " or "co tham quyen" in normalized or "co quan nao" in normalized:
        return "authority"
    if any(phrase in normalized for phrase in ("co phai", "hay khong", "co duoc", "co can", "co bat buoc")):
        return "yes_no"
    return "general"


def count_numeric_tokens(text: str) -> int:
    return sum(1 for token in tokenize(text) if token.isdigit())


def procedural_noise_score(text: str) -> float:
    normalized = normalized_text(text)
    return float(sum(1 for phrase in PROCEDURAL_NOISE_PHRASES if phrase in normalized))


def direct_answer_score(question: str, text: str) -> float:
    normalized = normalized_text(text)
    intent = detect_question_intent(question)
    score = 0.0

    if intent == "quantity":
        score += min(count_numeric_tokens(text), 3) * 0.8
        score += sum(0.55 for phrase in QUANTITY_ANSWER_PHRASES if phrase in normalized)
        if "nghi hang nam" in normalized or "phep nam" in normalized:
            score += 0.75
        score -= procedural_noise_score(text) * 0.55
    elif intent == "authority":
        score += sum(0.75 for phrase in AUTHORITY_ANSWER_PHRASES if phrase in normalized)
        if re.search(r"\b(giam doc|bo truong|chu tich|tong cuc truong|thu truong)\b", normalized):
            score += 1.1
        score -= procedural_noise_score(text) * 0.3
    elif intent == "yes_no":
        score += sum(0.6 for phrase in YES_NO_ANSWER_PHRASES if phrase in normalized)
        if "khong" in normalized:
            score += 0.3
        score -= procedural_noise_score(text) * 0.2
    else:
        score += keyword_coverage_score(question, text)
        score += phrase_coverage_score(question, text) * 1.5

    return score


def infer_document_title(text: str) -> str | None:
    lines = [normalize_text(line) for line in re.split(r"[\r\n]+", text or "") if normalize_text(line)]
    for line in lines[:8]:
        lowered = strip_accents(line).lower()
        if any(hint in lowered for hint in LEGAL_TITLE_HINTS) and len(line) <= 180:
            return line
    return None


def infer_yes_no_prefix(question: str, sentence: str) -> str | None:
    if detect_question_intent(question) != "yes_no":
        return None
    normalized = normalized_text(sentence)
    negative_markers = ("khong duoc", "khong phai", "khong co", "khong can", "cam")
    positive_markers = ("duoc", "phai", "co trach nhiem", "bat buoc", "co")
    if any(marker in normalized for marker in negative_markers):
        return "Khong."
    if any(marker in normalized for marker in positive_markers):
        return "Co."
    return None


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
