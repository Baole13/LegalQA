from __future__ import annotations

from src.utils.text import detect_article, detect_clause, infer_document_title


def format_citation(chunk: dict) -> dict:
    text = chunk.get("text", "")
    title = chunk.get("doc_name") or chunk.get("title") or infer_document_title(text)
    doc_number = chunk.get("doc_number")
    chapter = chunk.get("chapter")
    article = chunk.get("article") or detect_article(text)
    clause = chunk.get("clause") or detect_clause(text)
    return {
        "title": title,
        "doc_name": title,
        "doc_number": doc_number,
        "cid": chunk.get("cid"),
        "chapter": chapter,
        "article": article,
        "clause": clause,
        "issued_date": chunk.get("issued_date"),
        "effective_date": chunk.get("effective_date"),
        "validity_status": chunk.get("validity_status"),
        "chunk_level": chunk.get("chunk_level"),
        "chunk_id": chunk.get("chunk_id"),
        "sources": chunk.get("sources", []),
        "text": text,
        "label": _build_citation_label(
            title=title,
            doc_number=doc_number,
            chapter=chapter,
            article=article,
            clause=clause,
            validity_status=chunk.get("validity_status"),
        ),
    }


def _build_citation_label(
    title: str | None,
    doc_number: str | None,
    chapter: str | None,
    article: str | None,
    clause: str | None,
    validity_status: str | None,
) -> str:
    parts: list[str] = []
    if title:
        parts.append(title)
    if doc_number:
        parts.append(f"So {doc_number}")
    if chapter:
        parts.append(f"Chuong {chapter}")
    if article:
        parts.append(f"Dieu {article}")
    if clause:
        parts.append(f"Khoan {clause}")
    if validity_status:
        parts.append(validity_status)
    if not parts:
        return "Can cu phap ly trong corpus"
    return " | ".join(parts)
