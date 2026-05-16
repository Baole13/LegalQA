"""
Answer generation for legal QA system.

Provides extractive answer generation with citation tracking and confidence scoring.
Can optionally use LLM reasoning for improved answer quality.
"""

from __future__ import annotations

from collections import defaultdict

from src.qa.citation_formatter import format_citation
from src.qa.llm_reasoner import QwenReasoner
from src.qa.prompt_builder import build_reasoning_prompt
from src.utils.text import (
    detect_question_intent,
    direct_answer_score,
    infer_yes_no_prefix,
    important_query_phrases,
    keyword_coverage_score,
    phrase_coverage_score,
    procedural_noise_score,
    split_sentences,
    tokenize,
    unique_preserve_order,
)


class ExtractiveAnswerGenerator:
    """
    Generate extractive answers from retrieved legal documents.

    Features:
    - Extractive answer selection from top chunks
    - Automatic citation formatting
    - Confidence scoring
    - Optional LLM-based reasoning for complex questions
    - Similar question deduplication
    """

    def __init__(self, reasoner: QwenReasoner | None = None):
        self.reasoner = reasoner

    def generate(self, question: str, evidence_chunks: list[dict], similar_questions: list[dict] | None = None) -> dict:
        similar_questions = similar_questions or []
        if not evidence_chunks:
            return {
                "answer": self._format_no_evidence_answer(
                    "Chua tim thay du can cu phap ly phu hop trong corpus hien co de tra loi cau hoi nay."
                ),
                "citations": [],
                "evidence": [],
                "confidence": "low",
                "reason": "no_evidence",
            }

        query_tokens = set(tokenize(question))
        query_phrases = important_query_phrases(question)
        visible_chunks = self._visible_chunks_for_answer(evidence_chunks)
        evidence_sentences: list[tuple[float, str, dict]] = []
        for chunk in visible_chunks:
            for sentence in split_sentences(chunk.get("text", "")):
                sentence_tokens = set(tokenize(sentence))
                overlap = len(query_tokens.intersection(sentence_tokens))
                if overlap == 0:
                    continue
                coverage = keyword_coverage_score(question, sentence)
                phrase_coverage = phrase_coverage_score(question, sentence)
                direct_bonus = direct_answer_score(question, sentence)
                score = overlap + (coverage * 2.0) + (phrase_coverage * 5.0) + (direct_bonus * 1.8)
                evidence_sentences.append((score, sentence, chunk))

        evidence_sentences.sort(key=lambda item: item[0], reverse=True)
        top_coverage = max((keyword_coverage_score(question, chunk.get("text", "")) for chunk in visible_chunks[:3]), default=0.0)
        top_phrase_coverage = max((phrase_coverage_score(question, chunk.get("text", "")) for chunk in visible_chunks[:3]), default=0.0)
        top_rerank = float((visible_chunks or evidence_chunks)[0].get("rerank_score", 0.0))
        top_qa_boost = max((float(chunk.get("qa_boost", 0.0)) for chunk in visible_chunks[:3]), default=0.0)

        evidence = [
            {
                "chunk_id": chunk["chunk_id"],
                "cid": chunk["cid"],
                "text": chunk.get("text", ""),
                "score": chunk.get("rerank_score", chunk.get("hybrid_score")),
                "keyword_coverage": chunk.get("keyword_coverage", 0.0),
                "phrase_coverage": chunk.get("phrase_coverage", 0.0),
                "qa_boost": chunk.get("qa_boost", 0.0),
                "sources": chunk.get("sources", []),
            }
            for chunk in evidence_chunks[:5]
        ]

        if query_phrases and top_phrase_coverage == 0.0 and top_qa_boost < 0.15:
            return {
                "answer": self._format_no_evidence_answer(
                    "Chua tim thay can cu du sat voi cum phap ly trong cau hoi. Ket qua hien tai moi khop tu khoa roi rac."
                ),
                "citations": [],
                "evidence": evidence,
                "confidence": "low",
                "reason": "phrase_mismatch",
                "similar_questions": similar_questions[:3],
                "generator_mode": "extractive",
            }

        if top_coverage < 0.45 or top_rerank < 2.5:
            return {
                "answer": self._format_no_evidence_answer(
                    "Can cu tim duoc chua du manh de dua ra ket luan chac chan. Nen dien dat lai cau hoi hoac mo rong corpus lien quan."
                ),
                "citations": [],
                "evidence": evidence,
                "confidence": "low",
                "reason": "low_confidence",
                "similar_questions": similar_questions[:3],
                "generator_mode": "extractive",
            }

        citations = []
        seen_keys: set[tuple] = set()
        for chunk in visible_chunks[:5]:
            citation = format_citation(chunk)
            key = (
                citation.get("cid"),
                citation.get("article"),
                citation.get("clause"),
                citation.get("chunk_id"),
            )
            if key in seen_keys:
                continue
            seen_keys.add(key)
            citations.append(citation)
        citations = self._prioritize_corpus_citations(citations)[:3]

        confidence = "high" if top_phrase_coverage > 0 or top_qa_boost > 0.2 else "medium"
        quotes = self._build_quotes(question, evidence_sentences, citations)
        extractive_answer = self._build_structured_answer(question, visible_chunks, evidence_sentences, citations, quotes, confidence)

        llm_result = self._maybe_reason_with_llm(question, visible_chunks, citations, extractive_answer, quotes, confidence)
        if llm_result is not None:
            llm_citations = self._map_citations_from_llm(citations, llm_result)
            return {
                "answer": self._compose_answer_from_llm(llm_result, llm_citations, quotes, confidence),
                "citations": llm_citations,
                "quotes": quotes,
                "evidence": evidence,
                "confidence": llm_result.get("confidence", confidence),
                "reason": llm_result.get("reason", "ok"),
                "similar_questions": similar_questions[:3],
                "generator_mode": "qwen",
            }

        return {
            "answer": extractive_answer,
            "citations": citations,
            "quotes": quotes,
            "evidence": evidence,
            "confidence": confidence,
            "reason": "ok",
            "similar_questions": similar_questions[:3],
            "generator_mode": "extractive",
        }

    def _build_structured_answer(
        self,
        question: str,
        evidence_chunks: list[dict],
        evidence_sentences: list[tuple[float, str, dict]],
        citations: list[dict],
        quotes: list[dict],
        confidence: str,
    ) -> str:
        primary_chunk = self._select_primary_chunk(question, evidence_chunks)
        primary_cid = str((quotes[0].get("cid") if quotes else (primary_chunk or {}).get("cid", "")))
        primary_sentences = [
            sentence
            for _, sentence, chunk in evidence_sentences
            if str(chunk.get("cid", "")) == primary_cid
        ]
        supporting_sentences = [quote.get("text", "") for quote in quotes] + [sentence for _, sentence, _ in evidence_sentences]
        conclusion = self._build_direct_conclusion(question, primary_sentences or supporting_sentences)
        primary_citations = [item for item in citations if str(item.get("cid", "")) == primary_cid]
        legal_basis_citations = (primary_citations or citations)[:2]

        notes: list[str] = []
        if confidence != "high":
            notes.append("Can doi chieu them toan van dieu khoan goc truoc khi ap dung vao truong hop cu the.")
        if len({str(chunk.get("cid", "")) for chunk in evidence_chunks[:3]}) > 1 and not primary_citations:
            notes.append("Cau tra loi duoc tong hop tu nhieu can cu; uu tien doi chieu van ban co do phu hop cao nhat.")

        return "\n".join(
            [
                "Ket luan:",
                conclusion,
                "",
                "Can cu phap ly:",
                *[self._format_citation_line(item) for item in legal_basis_citations],
                "",
                "Trich dan:",
                *[f'- "{quote.get("text", "")}"' for quote in quotes[:2]],
                "",
                "Luu y ap dung:",
                *(f"- {note}" for note in (notes or ["Can doc toan van can cu duoc trich dan de ap dung dung ngu canh."])),
            ]
        ).strip()

    def _format_no_evidence_answer(self, message: str) -> str:
        return "\n".join(
            [
                "Ket luan:",
                "Toi khong biet.",
                message,
                "",
                "Can cu phap ly:",
                "- Chua du can cu phu hop trong corpus hien tai.",
                "",
                "Trich dan:",
                '- "Khong co doan evidence du manh de trich dan truc tiep."',
                "",
                "Luu y ap dung:",
                "- Nen dien dat lai cau hoi hoac bo sung van ban phap ly lien quan vao corpus.",
            ]
        )

    def _format_citation_line(self, citation: dict) -> str:
        return f"- {citation.get('label') or 'Can cu phap ly trong corpus'}"

    def _join_sentences(self, sentences: list[str]) -> str:
        if not sentences:
            return "Chua rut duoc ket luan ro rang tu evidence hien co."
        return " ".join(unique_preserve_order(sentences)).strip()

    def _prioritize_corpus_citations(self, citations: list[dict]) -> list[dict]:
        corpus_first = [item for item in citations if not str(item.get("chunk_id", "")).startswith("qa-memory:")]
        return corpus_first or citations

    def _visible_chunks_for_answer(self, evidence_chunks: list[dict]) -> list[dict]:
        corpus_chunks = [item for item in evidence_chunks if not str(item.get("chunk_id", "")).startswith("qa-memory:")]
        return corpus_chunks or evidence_chunks

    def _select_primary_chunk(self, question: str, evidence_chunks: list[dict]) -> dict | None:
        if not evidence_chunks:
            return None
        return max(
            evidence_chunks,
            key=lambda chunk: (
                direct_answer_score(question, chunk.get("text", "")) * 2.0
                + (keyword_coverage_score(question, chunk.get("text", "")) * 1.6)
                + (phrase_coverage_score(question, chunk.get("text", "")) * 3.0)
                + float(chunk.get("rerank_score", chunk.get("hybrid_score", 0.0)))
                - (procedural_noise_score(chunk.get("text", "")) * 0.5)
            ),
        )

    def _build_direct_conclusion(self, question: str, candidate_sentences: list[str]) -> str:
        if not candidate_sentences:
            return "Chua rut duoc ket luan ro rang tu evidence hien co."

        intent = detect_question_intent(question)
        ordered = unique_preserve_order(candidate_sentences)
        if intent in {"quantity", "authority", "yes_no"}:
            leading = ordered[0]
            if keyword_coverage_score(question, leading) >= 0.5:
                prefix = infer_yes_no_prefix(question, leading)
                if prefix and not leading.lower().startswith(("co.", "khong.")):
                    return f"{prefix} {leading}"
                return leading
        ranked = sorted(
            ordered,
            key=lambda sentence: (
                direct_answer_score(question, sentence) * 2.2
                + (keyword_coverage_score(question, sentence) * 1.5)
                + (phrase_coverage_score(question, sentence) * 2.0)
                - (procedural_noise_score(sentence) * 0.4)
            ),
            reverse=True,
        )
        best = ranked[0]
        prefix = infer_yes_no_prefix(question, best)
        if prefix and not best.lower().startswith(("co.", "khong.")):
            return f"{prefix} {best}"
        if intent in {"quantity", "authority", "yes_no"}:
            return best
        secondary = ranked[1] if len(ranked) > 1 and ranked[1] != best else None
        return " ".join([best, secondary] if secondary else [best]).strip()

    def _build_quotes(
        self,
        question: str,
        evidence_sentences: list[tuple[float, str, dict]],
        citations: list[dict],
    ) -> list[dict]:
        citation_by_chunk = {item.get("chunk_id"): item for item in citations}
        quotes: list[dict] = []
        seen: set[tuple[str, str]] = set()
        for _, sentence, chunk in evidence_sentences:
            key = (str(chunk.get("chunk_id")), sentence)
            if key in seen:
                continue
            citation = citation_by_chunk.get(chunk.get("chunk_id")) or format_citation(chunk)
            if str(citation.get("chunk_id", "")).startswith("qa-memory:"):
                continue
            seen.add(key)
            quotes.append(
                {
                    "text": sentence,
                    "chunk_id": citation.get("chunk_id"),
                    "cid": citation.get("cid"),
                    "title": citation.get("title"),
                    "article": citation.get("article"),
                    "clause": citation.get("clause"),
                    "label": citation.get("label"),
                    "detail_text": chunk.get("text", ""),
                    "score": round(direct_answer_score(question, sentence), 4),
                }
            )
            if len(quotes) >= 3:
                break
        return quotes

    def _maybe_reason_with_llm(
        self,
        question: str,
        evidence_chunks: list[dict],
        citations: list[dict],
        draft_answer: str,
        quotes: list[dict],
        confidence: str,
    ) -> dict | None:
        if self.reasoner is None or not self.reasoner.is_available():
            return None
        prompt = build_reasoning_prompt(question, evidence_chunks, draft_answer=draft_answer)
        result = self.reasoner.generate(prompt)
        if not result or not result.get("conclusion"):
            result = result or {}
        validated = self._validate_llm_result(result, citations, question, evidence_chunks, draft_answer)
        return validated

    def _map_citations_from_llm(self, citations: list[dict], llm_result: dict) -> list[dict]:
        wanted_ids = set(llm_result.get("citation_chunk_ids") or [])
        if not wanted_ids:
            return citations
        selected = [citation for citation in citations if citation.get("chunk_id") in wanted_ids]
        return selected or citations

    def _validate_llm_result(
        self,
        result: dict,
        citations: list[dict],
        question: str,
        evidence_chunks: list[dict],
        draft_answer: str,
    ) -> dict | None:
        conclusion = str(result.get("conclusion", "")).strip()
        if not conclusion:
            return None
        allowed_ids = {citation.get("chunk_id") for citation in citations}
        selected_ids = [chunk_id for chunk_id in (result.get("citation_chunk_ids") or []) if chunk_id in allowed_ids]
        confidence = str(result.get("confidence", "medium")).lower()
        if confidence not in {"low", "medium", "high"}:
            confidence = "medium"

        intent = detect_question_intent(question)
        direct_score = direct_answer_score(question, conclusion)
        question_coverage = keyword_coverage_score(question, conclusion)
        if intent in {"quantity", "authority"} and (direct_score < 1.0 or question_coverage < 0.4):
            return None
        if intent == "yes_no" and (direct_score < 0.5 or question_coverage < 0.2):
            return None

        draft_conclusion = self._extract_conclusion_from_answer(draft_answer)
        if draft_conclusion:
            draft_alignment = max(
                keyword_coverage_score(draft_conclusion, conclusion),
                keyword_coverage_score(conclusion, draft_conclusion),
            )
            if draft_alignment < 0.35:
                return None

        evidence_pool = " ".join(chunk.get("text", "") for chunk in evidence_chunks[:3])
        if draft_conclusion:
            evidence_alignment = max(
                keyword_coverage_score(conclusion, evidence_pool),
                keyword_coverage_score(question, evidence_pool),
            )
            if evidence_alignment < 0.35:
                return None

        notes = [
            str(note).strip()
            for note in (result.get("notes") or [])
            if str(note).strip() and len(str(note).strip()) <= 220
        ][:2]
        return {
            "conclusion": conclusion,
            "confidence": confidence,
            "reason": str(result.get("reason", "ok")),
            "citation_chunk_ids": selected_ids,
            "notes": notes,
        }

    def _compose_answer_from_llm(
        self,
        llm_result: dict,
        citations: list[dict],
        quotes: list[dict],
        fallback_confidence: str,
    ) -> str:
        notes = list(llm_result.get("notes") or [])
        if not notes and (llm_result.get("confidence") or fallback_confidence) != "high":
            notes.append("Can doi chieu them toan van dieu khoan goc truoc khi ap dung vao truong hop cu the.")
        if not notes:
            notes.append("Can doc toan van can cu duoc trich dan de ap dung dung ngu canh.")
        return "\n".join(
            [
                "Ket luan:",
                str(llm_result.get("conclusion", "")).strip(),
                "",
                "Can cu phap ly:",
                *[self._format_citation_line(item) for item in citations[:2]],
                "",
                "Trich dan:",
                *[f'- "{quote.get("text", "")}"' for quote in quotes[:2]],
                "",
                "Luu y ap dung:",
                *(f"- {note}" for note in notes),
            ]
        ).strip()

    def _extract_conclusion_from_answer(self, answer: str) -> str:
        lines = [line.strip() for line in str(answer or "").splitlines()]
        if "Ket luan:" not in lines:
            return ""
        index = lines.index("Ket luan:")
        for line in lines[index + 1 :]:
            if not line or line.endswith(":"):
                continue
            return line
        return ""
