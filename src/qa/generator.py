"""
Answer generation for legal QA system.

Provides extractive answer generation with citation tracking and confidence scoring.
Can optionally use LLM reasoning for improved answer quality.
"""

from __future__ import annotations

from src.qa.citation_formatter import format_citation
from src.qa.llm_reasoner import QwenReasoner
from src.qa.prompt_builder import build_reasoning_prompt
from src.utils.text import (
    important_query_phrases,
    keyword_coverage_score,
    phrase_coverage_score,
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
        """
        Initialize answer generator.

        Args:
            reasoner: Optional LLM reasoner for generating better answers
        """
        self.reasoner = reasoner

    def generate(self, question: str, evidence_chunks: list[dict], similar_questions: list[dict] | None = None) -> dict:
        """
        Generate an answer based on evidence chunks.

        Args:
            question: Legal question in Vietnamese
            evidence_chunks: Ranked list of relevant document chunks
            similar_questions: Optional list of similar previous questions

        Returns:
            Dictionary with answer, citations, confidence, and metadata
        """
        similar_questions = similar_questions or []
        if not evidence_chunks:
            return {
                "answer": "Không tìm thấy đủ căn cứ pháp lý phù hợp trong corpus hiện có để trả lời câu hỏi này.",
                "citations": [],
                "evidence": [],
                "confidence": "low",
                "reason": "no_evidence",
            }

        query_tokens = set(tokenize(question))
        query_phrases = important_query_phrases(question)
        evidence_sentences: list[tuple[float, str, dict]] = []
        for chunk in evidence_chunks:
            for sentence in split_sentences(chunk.get("text", "")):
                sentence_tokens = set(tokenize(sentence))
                overlap = len(query_tokens.intersection(sentence_tokens))
                if overlap == 0:
                    continue
                coverage = keyword_coverage_score(question, sentence)
                phrase_coverage = phrase_coverage_score(question, sentence)
                score = overlap + (coverage * 2.0) + (phrase_coverage * 5.0)
                evidence_sentences.append((score, sentence, chunk))

        evidence_sentences.sort(key=lambda item: item[0], reverse=True)
        top_coverage = max((keyword_coverage_score(question, chunk.get("text", "")) for chunk in evidence_chunks[:3]), default=0.0)
        top_phrase_coverage = max((phrase_coverage_score(question, chunk.get("text", "")) for chunk in evidence_chunks[:3]), default=0.0)
        top_rerank = float(evidence_chunks[0].get("rerank_score", 0.0))
        top_qa_boost = max((float(chunk.get("qa_boost", 0.0)) for chunk in evidence_chunks[:3]), default=0.0)

        evidence = [
            {
                "chunk_id": chunk["chunk_id"],
                "cid": chunk["cid"],
                "text": chunk.get("text", ""),
                "score": chunk.get("rerank_score", chunk.get("hybrid_score")),
                "keyword_coverage": chunk.get("keyword_coverage", 0.0),
                "phrase_coverage": chunk.get("phrase_coverage", 0.0),
                "qa_boost": chunk.get("qa_boost", 0.0),
            }
            for chunk in evidence_chunks[:3]
        ]

        if query_phrases and top_phrase_coverage == 0.0 and top_qa_boost < 0.15:
            return {
                "answer": "Chưa tìm thấy căn cứ đủ sát trong corpus hiện có để trả lời chắc chắn câu hỏi này. Các đoạn tìm được mới khớp từ khóa rời rạc, chưa khớp đúng cụm pháp lý cần hỏi.",
                "citations": [],
                "evidence": evidence,
                "confidence": "low",
                "reason": "phrase_mismatch",
                "similar_questions": similar_questions[:3],
                "generator_mode": "extractive",
            }

        if top_coverage < 0.45 or top_rerank < 2.5:
            return {
                "answer": "Chưa tìm thấy căn cứ đủ mạnh trong corpus hiện có để trả lời chắc chắn câu hỏi này. Bạn có thể diễn đạt lại câu hỏi hoặc mở rộng corpus pháp luật liên quan.",
                "citations": [],
                "evidence": evidence,
                "confidence": "low",
                "reason": "low_confidence",
                "similar_questions": similar_questions[:3],
                "generator_mode": "extractive",
            }

        citations = []
        seen_keys: set[tuple] = set()
        for chunk in evidence_chunks[:3]:
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

        confidence = "high" if top_phrase_coverage > 0 or top_qa_boost > 0.2 else "medium"
        extractive_answer = self._build_extractive_answer(question, evidence_chunks, evidence_sentences)

        llm_result = self._maybe_reason_with_llm(question, evidence_chunks, citations)
        if llm_result is not None:
            return {
                "answer": llm_result.get("answer", extractive_answer),
                "citations": self._map_citations_from_llm(citations, llm_result),
                "evidence": evidence,
                "confidence": llm_result.get("confidence", confidence),
                "reason": llm_result.get("reason", "ok"),
                "similar_questions": similar_questions[:3],
                "generator_mode": "qwen",
            }

        return {
            "answer": extractive_answer,
            "citations": citations,
            "evidence": evidence,
            "confidence": confidence,
            "reason": "ok",
            "similar_questions": similar_questions[:3],
            "generator_mode": "extractive",
        }

    def _build_extractive_answer(self, question: str, evidence_chunks: list[dict], evidence_sentences: list[tuple[float, str, dict]]) -> str:
        if evidence_sentences:
            chosen = evidence_sentences[:4]
            return " ".join(unique_preserve_order(sentence for _, sentence, _ in chosen))
        return evidence_chunks[0].get("text", "")[:700].strip()

    def _maybe_reason_with_llm(self, question: str, evidence_chunks: list[dict], citations: list[dict]) -> dict | None:
        if self.reasoner is None or not self.reasoner.is_available():
            return None
        prompt = build_reasoning_prompt(question, evidence_chunks)
        result = self.reasoner.generate(prompt)
        if not result or not result.get("answer"):
            return None
        return result

    def _map_citations_from_llm(self, citations: list[dict], llm_result: dict) -> list[dict]:
        wanted_ids = set(llm_result.get("citation_chunk_ids") or [])
        if not wanted_ids:
            return citations
        selected = [citation for citation in citations if citation.get("chunk_id") in wanted_ids]
        return selected or citations
