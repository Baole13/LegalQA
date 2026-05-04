from __future__ import annotations

import json


def build_reasoning_prompt(question: str, evidence_chunks: list[dict]) -> str:
    evidence = []
    for chunk in evidence_chunks[:4]:
        evidence.append(
            {
                "chunk_id": chunk.get("chunk_id"),
                "cid": chunk.get("cid"),
                "article": chunk.get("article"),
                "clause": chunk.get("clause"),
                "text": chunk.get("text", ""),
            }
        )

    return f"""
Bạn là trợ lý pháp lý tiếng Việt. Chỉ được trả lời dựa trên evidence đã cho.

Yêu cầu:
1. Không bịa thông tin ngoài evidence.
2. Nếu evidence chưa đủ chắc chắn, phải nói rõ là chưa đủ căn cứ.
3. Trích dẫn theo chunk_id/cid tương ứng.
4. Trả về JSON hợp lệ với schema:
{{
  "answer": "string",
  "confidence": "low|medium|high",
  "reason": "string",
  "citation_chunk_ids": ["string"]
}}

Câu hỏi:
{question}

Evidence:
{json.dumps(evidence, ensure_ascii=False, indent=2)}
""".strip()
