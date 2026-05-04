from __future__ import annotations


def format_citation(chunk: dict) -> dict:
    return {
        "title": chunk.get("title") or f"Văn bản CID {chunk.get('cid')}",
        "cid": chunk.get("cid"),
        "article": chunk.get("article"),
        "clause": chunk.get("clause"),
        "chunk_id": chunk.get("chunk_id"),
    }
