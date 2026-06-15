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

Muc tieu:
- Tra loi ngan, truc tiep, dung trong ngu canh hoi dap phap luat.
- Phai neu can cu phap ly va chunk_id/cid ro rang.
- Phai giai thich ngan vi sao can cu do dan den ket luan.
- Khong duoc dua ra thong tin ngoai evidence.
- Neu khong du can cu de ket luan, phai noi ro "Toi khong biet" va neu thong tin con thieu.

Quy tac bat buoc:
1. Moi ket luan phai co it nhat 1 can cu va 1 trich dan neu evidence du.
2. Khong qua 2 can cu chinh va khong qua 2 trich dan manh nhat.
3. Neu cau hoi la quantity/authority/yes_no, phai tra loi truc tiep va khong vong vo.
4. Neu evidence khong khop true y cau hoi, phai noi ro khong du can cu.
5. Neu evidence co doan dung y truc tiep, phai uu tien doan do thay vi dien giai xa.
6. Phai co cau noi logic nhu: "do do", "vi vay", "theo do", "tu do", "suy ra" khi phu hop.
7. missing_info khong duoc de rong; neu khong co thi ghi "Khong co them thong tin can bo sung."

Du lieu vao:
- Cau hoi: {question}
- Loai cau hoi: {question_intent}
- Ban nhap tam thoi: {draft_answer}

Evidence:
{json.dumps(evidence, ensure_ascii=False, indent=2)}

BAT BUOC: Tra ve JSON ONLY. Khong markdown. Khong giai thich ngoai JSON. Khong lap lai prompt.
Schema JSON:
{{
  "answer": "string",
  "legal_basis": ["string"],
  "reasoning": "string",
  "missing_info": ["string"],
  "citation_chunk_ids": ["string"],
  "confidence": "low|medium|high",
  "reason": "string"
}}

Yeu cau ve answer:
- Mot den ba cau, tra loi thang vao cau hoi.
- Neu khong du can cu, answer bat dau bang "Toi khong biet."
- Khong chen chain-of-thought dai; reasoning chi la giai thich ngan dua tren evidence.
- Vi du dang tra ve: {{"answer":"...","legal_basis":["..."],"reasoning":"...","missing_info":["..."],"citation_chunk_ids":["..."],"confidence":"high","reason":"..."}}

JSON ONLY:
""".strip()
