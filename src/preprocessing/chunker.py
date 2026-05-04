from __future__ import annotations

from src.preprocessing.clean_text import clean_text, is_valid_text
from src.utils.text import detect_article, detect_clause


def build_chunks_from_corpus(records: list[dict], max_chars: int = 1200, overlap_chars: int = 120) -> list[dict]:
    chunks: list[dict] = []
    for record in records:
        cid = str(record["cid"])
        text = clean_text(str(record.get("text", "")))
        if not is_valid_text(text):
            continue
        if len(text) <= max_chars:
            chunks.append(_make_chunk(cid=cid, text=text, part=0))
            continue
        start = 0
        part = 0
        while start < len(text):
            end = min(len(text), start + max_chars)
            window = text[start:end].strip()
            if is_valid_text(window):
                chunks.append(_make_chunk(cid=cid, text=window, part=part))
                part += 1
            if end >= len(text):
                break
            start = max(0, end - overlap_chars)
    return chunks


def _make_chunk(cid: str, text: str, part: int) -> dict:
    article = detect_article(text)
    clause = detect_clause(text)
    chunk_id = cid if part == 0 else f"{cid}:{part}"
    return {
        "chunk_id": chunk_id,
        "doc_id": cid,
        "cid": cid,
        "title": f"Văn bản CID {cid}",
        "article": article,
        "clause": clause,
        "text": text,
        "token_len": len(text.split()),
    }

