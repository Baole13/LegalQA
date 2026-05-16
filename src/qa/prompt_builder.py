from __future__ import annotations

import json

from src.utils.text import detect_question_intent


def build_reasoning_prompt(question: str, evidence_chunks: list[dict], draft_answer: str = "") -> str:
    question_intent = detect_question_intent(question)
    evidence = []
    for chunk in evidence_chunks[:5]:
        evidence.append(
            {
                "chunk_id": chunk.get("chunk_id"),
                "cid": chunk.get("cid"),
                "doc_name": chunk.get("doc_name") or chunk.get("title"),
                "doc_number": chunk.get("doc_number"),
                "chapter": chunk.get("chapter"),
                "article": chunk.get("article"),
                "clause": chunk.get("clause"),
                "effective_date": chunk.get("effective_date"),
                "validity_status": chunk.get("validity_status"),
                "text": chunk.get("text", ""),
                "sources": chunk.get("sources", []),
            }
        )

    return f"""
Ban la tro ly phap ly tieng Viet. Chi duoc tra loi dua tren evidence da cho.

Yeu cau:
1. Khong dua them thong tin ngoai evidence.
2. Neu evidence khong chua cau tra loi hoac chua du chac chan, phai ket luan chinh xac la "Toi khong biet".
3. Phai uu tien tra loi truc tiep dung dang cau hoi:
   - quantity: tra loi truc tiep bang so lieu/muc/thoi han neu evidence co.
   - authority: neu cau hoi hoi "ai/co quan nao co tham quyen", phai neu ro chu the ngay cau dau.
   - yes_no: phai mo dau bang "Co." hoac "Khong." neu evidence du ro.
4. Tra loi dung format duoi day:
Ket luan:
...

Can cu phap ly:
- ...

Trich dan:
- "..."

Luu y ap dung:
- ...
5. Trich dan theo chunk_id/cid tuong ung.
6. Chi duoc su dung toi da 2 can cu chinh va 2 trich dan manh nhat.
7. Neu evidence co doan dung y hoi truc tiep, phai uu tien doan do thay vi dien giai vong vo.
8. Khong duoc suy doan tu kien thuc ngoai corpus, ke ca khi ban da biet cau tra loi tu truoc.
9. Tra ve JSON hop le voi schema:
{{
  "conclusion": "string",
  "confidence": "low|medium|high",
  "reason": "string",
  "citation_chunk_ids": ["string"],
  "notes": ["string"]
}}

Cau hoi:
{question}

Loai cau hoi:
{question_intent}

Ban nhap tam thoi:
{draft_answer}

Evidence:
{json.dumps(evidence, ensure_ascii=False, indent=2)}
""".strip()
