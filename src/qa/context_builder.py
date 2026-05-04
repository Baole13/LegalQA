from __future__ import annotations


def build_context(chunks: list[dict], top_k: int = 3) -> str:
    selected = chunks[:top_k]
    blocks = []
    for chunk in selected:
        blocks.append(
            "\n".join(
                [
                    f"[CID: {chunk.get('cid')} | Điều: {chunk.get('article') or '?'} | Khoản: {chunk.get('clause') or '?'} | Score: {chunk.get('rerank_score', chunk.get('hybrid_score', 0))}]",
                    chunk.get("text", ""),
                ]
            )
        )
    return "\n\n".join(blocks)
