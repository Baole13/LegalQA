from __future__ import annotations

import re

from src.preprocessing.clean_text import is_valid_text
from src.preprocessing.legal_metadata import build_legal_metadata, metadata_to_dict, normalize_legal_record
from src.utils.text import normalize_text

ARTICLE_SPLIT_PATTERN = re.compile(r"(?=(?:^|\n)\s*Dieu\s+\d+[A-Za-z]?(?:[.:]|\s))", re.IGNORECASE)
ARTICLE_INLINE_PATTERN = re.compile(r"(?:^|\n)\s*Dieu\s+(\d+[A-Za-z]?)", re.IGNORECASE)
CLAUSE_LINE_PATTERN = re.compile(r"^\s*(\d+)[.)]\s+", re.MULTILINE)


def build_chunks_from_corpus(
    records: list[dict],
    max_chars: int = 1600,
    overlap_chars: int = 120,
) -> list[dict]:
    chunks: list[dict] = []
    for record in records:
        normalized = normalize_legal_record(record)
        cid = str(normalized.get("cid") or "")
        text = _clean_legal_text(str(normalized.get("text", "")))
        if not cid or not is_valid_text(text):
            continue

        article_sections = _split_articles(text)
        if not article_sections:
            article_sections = [(_detect_article(text), text)]

        part = 0
        for article, article_text in article_sections:
            clause_sections = _split_clauses(article_text)
            if not clause_sections:
                clause_sections = [(_detect_clause(article_text), article_text)]
            for clause, clause_text in clause_sections:
                windows = _split_large_text(clause_text, max_chars=max_chars, overlap_chars=overlap_chars)
                chunk_level = "clause" if clause else "article"
                for window_index, window_text in enumerate(windows):
                    if not is_valid_text(window_text):
                        continue
                    chunks.append(
                        _make_chunk(
                            record=normalized,
                            text=window_text,
                            part=part,
                            article=article,
                            clause=clause,
                            chunk_level=chunk_level,
                            subpart=window_index if len(windows) > 1 else None,
                        )
                    )
                    part += 1
    return chunks


def _split_articles(text: str) -> list[tuple[str | None, str]]:
    sections = [section.strip() for section in ARTICLE_SPLIT_PATTERN.split(text or "") if section.strip()]
    if len(sections) <= 1:
        article = _detect_article(text)
        return [(article, text)] if text.strip() else []
    results: list[tuple[str | None, str]] = []
    for section in sections:
        results.append((_detect_article(section), section))
    return results


def _split_clauses(article_text: str) -> list[tuple[str | None, str]]:
    matches = list(CLAUSE_LINE_PATTERN.finditer(article_text or ""))
    if len(matches) <= 1:
        clause = _detect_clause(article_text)
        return [(clause, article_text)] if article_text.strip() else []

    sections: list[tuple[str | None, str]] = []
    header = article_text[: matches[0].start()].strip()
    for index, match in enumerate(matches):
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(article_text)
        clause_text = article_text[start:end].strip()
        if header:
            clause_text = f"{header}\n{clause_text}"
        sections.append((match.group(1), clause_text))
    return sections


def _split_large_text(text: str, max_chars: int, overlap_chars: int) -> list[str]:
    if len(text) <= max_chars:
        return [text.strip()]
    windows: list[str] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + max_chars)
        window = text[start:end].strip()
        if window:
            windows.append(window)
        if end >= len(text):
            break
        start = max(0, end - overlap_chars)
    return windows


def _clean_legal_text(text: str) -> str:
    lines = [normalize_text(line) for line in str(text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    cleaned = "\n".join(line for line in lines if line)
    return cleaned.strip()


def _make_chunk(
    record: dict,
    text: str,
    part: int,
    article: str | None,
    clause: str | None,
    chunk_level: str,
    subpart: int | None,
) -> dict:
    metadata = build_legal_metadata(record, article=article, clause=clause)
    chunk_id = metadata.cid if part == 0 else f"{metadata.cid}:{part}"
    if subpart is not None:
        chunk_id = f"{chunk_id}.p{subpart}"
    payload = metadata_to_dict(metadata)
    payload.update(
        {
            "chunk_id": chunk_id,
            "doc_id": metadata.cid,
            "title": metadata.doc_name,
            "chunk_level": chunk_level,
            "text": text,
            "token_len": len(text.split()),
        }
    )
    return payload


def _detect_article(text: str) -> str | None:
    match = ARTICLE_INLINE_PATTERN.search(text or "")
    return match.group(1) if match else None


def _detect_clause(text: str) -> str | None:
    match = CLAUSE_LINE_PATTERN.search(text or "")
    return match.group(1) if match else None
