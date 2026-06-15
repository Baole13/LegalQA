"""
Answer generation for legal QA system.

Provides extractive answer generation with citation tracking and confidence scoring.
Can optionally use LLM reasoning for improved answer quality.
"""

from __future__ import annotations

from collections import defaultdict
import re

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
    topic_anchor_score,
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

    def generate(
        self,
        question: str,
        evidence_chunks: list[dict],
        similar_questions: list[dict] | None = None,
        force_llm_reasoning: bool = False,
        debug_llm: bool = False,
    ) -> dict:
        similar_questions = similar_questions or []
        if not evidence_chunks:
            return self._no_evidence_result(
                "Chua tim thay du can cu phap ly phu hop trong corpus hien co de tra loi cau hoi nay.",
                reason="no_evidence",
            )

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
                anchor_bonus = topic_anchor_score(question, sentence)
                score = overlap + (coverage * 2.0) + (phrase_coverage * 5.0) + (direct_bonus * 1.8) + (anchor_bonus * 2.0)
                evidence_sentences.append((score, sentence, chunk))

        evidence_sentences.sort(key=lambda item: item[0], reverse=True)
        top_coverage = max((keyword_coverage_score(question, chunk.get("text", "")) for chunk in visible_chunks[:3]), default=0.0)
        top_phrase_coverage = max((phrase_coverage_score(question, chunk.get("text", "")) for chunk in visible_chunks[:3]), default=0.0)
        top_anchor = max((topic_anchor_score(question, chunk.get("text", "")) for chunk in visible_chunks[:3]), default=0.0)
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
            result = self._no_evidence_result(
                "Chua tim thay can cu du sat voi cum phap ly trong cau hoi. Ket qua hien tai moi khop tu khoa roi rac.",
                reason="phrase_mismatch",
                evidence=evidence,
            )
            result["similar_questions"] = similar_questions[:3]
            return result

        if top_coverage < 0.45 or top_rerank < 2.5 or (detect_question_intent(question) == "quantity" and top_anchor < 0):
            result = self._no_evidence_result(
                "Can cu tim duoc chua du manh de dua ra ket luan chac chan. Nen dien dat lai cau hoi hoac mo rong corpus lien quan.",
                reason="low_confidence",
                evidence=evidence,
            )
            result["similar_questions"] = similar_questions[:3]
            return result

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
        answer_payload = self._build_answer_payload(question, visible_chunks, evidence_sentences, citations, quotes, confidence)
        extractive_answer = answer_payload["answer"]

        llm_result = self._maybe_reason_with_llm(
            question,
            visible_chunks,
            citations,
            extractive_answer,
            quotes,
            confidence,
            force_llm_reasoning=force_llm_reasoning,
        )
        if llm_result is not None:
            llm_citations = self._map_citations_from_llm(citations, llm_result)
            return {
                "answer": str(llm_result.get("answer", "")).strip(),
                "legal_basis": llm_result.get("legal_basis", []),
                "reasoning": llm_result.get("reasoning", ""),
                "missing_info": llm_result.get("missing_info", []),
                "citations": llm_citations,
                "quotes": quotes,
                "evidence": evidence,
                "confidence": llm_result.get("confidence", confidence),
                "reason": llm_result.get("reason", "ok"),
                "similar_questions": similar_questions[:3],
                "generator_mode": "qwen",
                **({"llm_debug": llm_result.get("llm_debug", {})} if debug_llm else {}),
            }

        return {
            **answer_payload,
            "citations": citations,
            "quotes": quotes,
            "evidence": evidence,
            "reason": "ok",
            "similar_questions": similar_questions[:3],
            "generator_mode": "extractive",
            **({"llm_debug": self._last_llm_debug("fallback_extractive")} if debug_llm else {}),
        }


    def _build_answer_payload(
        self,
        question: str,
        evidence_chunks: list[dict],
        evidence_sentences: list[tuple[float, str, dict]],
        citations: list[dict],
        quotes: list[dict],
        confidence: str,
    ) -> dict:
        primary_chunk = self._select_primary_chunk(question, evidence_chunks)
        primary_cid = str((quotes[0].get("cid") if quotes else (primary_chunk or {}).get("cid", "")))
        primary_sentences = [
            sentence
            for _, sentence, chunk in evidence_sentences
            if str(chunk.get("cid", "")) == primary_cid
        ]
        supporting_sentences = [quote.get("text", "") for quote in quotes] + [sentence for _, sentence, _ in evidence_sentences]
        answer = self._build_direct_conclusion(question, primary_sentences or supporting_sentences)
        primary_citations = [item for item in citations if str(item.get("cid", "")) == primary_cid]
        legal_basis_citations = (primary_citations or citations)[:2]
        legal_basis = [self._format_citation_line(item) for item in legal_basis_citations]

        if not legal_basis:
            return self._no_evidence_result(
                "Chua tim thay can cu phap ly phu hop de tra loi truc tiep.",
                reason="no_citation",
                confidence=confidence,
            )

        reasoning = self._build_concise_reasoning(question, answer, legal_basis, confidence)
        missing_info = ["Khong co them thong tin can bo sung."]
        if confidence != "high":
            missing_info = ["Can doi chieu them toan van dieu khoan goc truoc khi ap dung vao truong hop cu the."]

        return {
            "answer": answer,
            "legal_basis": legal_basis,
            "reasoning": reasoning,
            "missing_info": missing_info,
            "confidence": confidence,
        }

    def _no_evidence_result(
        self,
        message: str,
        reason: str,
        evidence: list[dict] | None = None,
        confidence: str = "low",
    ) -> dict:
        return {
            "answer": f"Toi khong biet. {message}",
            "legal_basis": [],
            "reasoning": "Khong co evidence du sat trong top-k nen khong the suy ra ket luan phap ly dang tin cay.",
            "missing_info": ["Can bo sung hoac truy van dung van ban phap ly lien quan hon."],
            "citations": [],
            "evidence": evidence or [],
            "confidence": confidence if confidence in {"low", "medium", "high"} else "low",
            "reason": reason,
            "generator_mode": "extractive",
        }

    def _build_concise_reasoning(self, question: str, answer: str, legal_basis: list[str], confidence: str) -> str:
        basis = legal_basis[0] if legal_basis else "evidence duoc truy van"
        if confidence == "high":
            return f"Can cu {basis} khop truc tiep voi noi dung cau hoi, vi vay co the ket luan nhu tren."
        return f"Can cu {basis} co lien quan den cau hoi; tuy nhien muc do khop chua cao nen ket luan can duoc doi chieu them."

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

        legal_basis_lines = [self._format_citation_line(item) for item in legal_basis_citations]
        conditions_lines = self._build_conditions_lines(question, evidence_chunks, legal_basis_citations)
        application_lines = self._build_application_lines(question, supporting_sentences, confidence)
        missing_lines = notes or ["Khong co them thong tin can bo sung."]
        return "\n".join(
            [
                "Can cu phap ly:",
                *[f"- {line}" for line in (legal_basis_lines or ["Chua du can cu phap ly phu hop trong corpus hien co."])],
                "",
                "Dieu kien phap ly lien quan:",
                *[f"- {line}" for line in (conditions_lines or ["Chua xac dinh du dieu kien phap ly ro rang."])],
                "",
                "Ap dung vao tinh huong:",
                *[f"- {line}" for line in (application_lines or ["Chua du du lieu de ap dung vao tinh huong cu the."])],
                "",
                "Ket luan:",
                f"- {conclusion}",
                "",
                "Thong tin con thieu:",
                *[f"- {line}" for line in missing_lines],
            ]
        ).strip()

    def _format_no_evidence_answer(self, message: str) -> str:
        return "\n".join(
            [
                "Can cu phap ly:",
                "- Chua du can cu phu hop trong corpus hien tai.",
                "",
                "Dieu kien phap ly lien quan:",
                "- Khong xac dinh duoc dieu kien ap dung vi thieu evidence.",
                "",
                "Ap dung vao tinh huong:",
                "- Khong the ap dung chan chac khi chua co evidence phu hop.",
                "",
                "Ket luan:",
                "- Toi khong biet.",
                f"- {message}",
                "",
                "Thong tin con thieu:",
                "- Nen dien dat lai cau hoi hoac bo sung van ban phap ly lien quan vao corpus.",
            ]
        )

    def _format_citation_line(self, citation: dict) -> str:
        return str(citation.get("label") or "Can cu phap ly trong corpus")

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
                (topic_anchor_score(question, chunk.get("text", "")) * 3.2)
                + (direct_answer_score(question, chunk.get("text", "")) * 2.0)
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
        if intent in {"authority", "yes_no"}:
            leading = ordered[0]
            if keyword_coverage_score(question, leading) >= 0.5:
                prefix = infer_yes_no_prefix(question, leading)
                if prefix and not leading.lower().startswith(("co.", "khong.")):
                    return f"{prefix} {leading}"
                return leading
        ranked = sorted(
            ordered,
            key=lambda sentence: (
                (topic_anchor_score(question, sentence) * 3.0)
                + (direct_answer_score(question, sentence) * 2.2)
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
        max_anchor = max((topic_anchor_score(question, sentence) for _, sentence, _ in evidence_sentences), default=0.0)
        quotes: list[dict] = []
        seen: set[tuple[str, str]] = set()
        for _, sentence, chunk in evidence_sentences:
            if max_anchor > 0 and topic_anchor_score(question, sentence) < max_anchor:
                continue
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
        force_llm_reasoning: bool = False,
    ) -> dict | None:
        if self.reasoner is None or not self.reasoner.is_available():
            return None
        prompt = build_reasoning_prompt(question, evidence_chunks, draft_answer=draft_answer)
        result = self.reasoner.generate(prompt)
        if force_llm_reasoning and (not result or not (result.get("answer") or result.get("conclusion"))):
            raw_text = str(getattr(self.reasoner, "last_raw_text", "") or "").strip()
            if raw_text:
                return self._coerce_raw_forced_llm_result(raw_text, citations, confidence)
            return None
        if not result or not (result.get("answer") or result.get("conclusion")):
            return None
        if force_llm_reasoning:
            return self._coerce_forced_llm_result(result, citations, confidence)
        validated = self._validate_llm_result(result, citations, question, evidence_chunks, draft_answer)
        if validated is not None:
            validated["llm_debug"] = self._last_llm_debug("accepted")
        return validated


    def _coerce_forced_llm_result(self, result: dict, citations: list[dict], fallback_confidence: str) -> dict:
        answer = str(result.get("answer") or result.get("conclusion") or "").strip()
        confidence = str(result.get("confidence") or fallback_confidence or "medium").lower()
        if confidence not in {"low", "medium", "high"}:
            confidence = "medium"
        legal_basis = self._normalize_lines(result.get("legal_basis"))
        if not legal_basis:
            legal_basis = [self._format_citation_line(item) for item in citations[:2]]
        missing_info = self._normalize_lines(result.get("missing_info")) or ["Khong co them thong tin can bo sung."]
        reasoning = str(result.get("reasoning") or " ".join(self._normalize_lines(result.get("application"))) or "LLM da suy luan dua tren evidence duoc cung cap.").strip()
        allowed_ids = {citation.get("chunk_id") for citation in citations}
        selected_ids = [chunk_id for chunk_id in (result.get("citation_chunk_ids") or []) if chunk_id in allowed_ids]
        return {
            "answer": answer,
            "conclusion": answer,
            "confidence": confidence,
            "reason": str(result.get("reason", "forced_llm")),
            "citation_chunk_ids": selected_ids,
            "legal_basis": legal_basis,
            "reasoning": reasoning,
            "missing_info": missing_info,
            "llm_debug": self._last_llm_debug("forced"),
        }

    def _coerce_raw_forced_llm_result(self, raw_text: str, citations: list[dict], fallback_confidence: str) -> dict:
        sentences = split_sentences(raw_text)
        answer = raw_text
        reasoning_sentences = []
        conclusion_markers = ("do do", "do đó", "vi vay", "vì vậy", "theo do", "theo đó")
        for sentence in sentences:
            normalized = sentence.strip().lower()
            if normalized.startswith(conclusion_markers):
                answer = sentence.strip()
            else:
                reasoning_sentences.append(sentence.strip())
        basis_match = re.search(r"Theo\s+(.{8,120}?),\s", raw_text, flags=re.IGNORECASE)
        legal_basis = [basis_match.group(1).strip()] if basis_match else [self._format_citation_line(item) for item in citations[:2]]
        reasoning = " ".join(item for item in reasoning_sentences if item and item != answer).strip()
        if not reasoning:
            reasoning = "LLM da suy luan truc tiep tu evidence duoc cung cap."
        confidence = fallback_confidence if fallback_confidence in {"low", "medium", "high"} else "medium"
        return {
            "answer": answer,
            "conclusion": answer,
            "confidence": confidence,
            "reason": "forced_raw_llm",
            "citation_chunk_ids": [],
            "legal_basis": legal_basis,
            "reasoning": reasoning,
            "missing_info": ["Khong co them thong tin can bo sung."],
            "llm_debug": self._last_llm_debug("forced_raw"),
        }

    def _last_llm_debug(self, status: str) -> dict:
        if self.reasoner is None:
            return {"status": status, "available": False}
        return {
            "status": status,
            "available": self.reasoner.loaded,
            "load_error": self.reasoner.load_error,
            "raw_text": getattr(self.reasoner, "last_raw_text", ""),
            "parsed": getattr(self.reasoner, "last_parsed", None),
        }

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
        answer = str(result.get("answer") or result.get("conclusion", "")).strip()
        if not answer:
            return None
        allowed_ids = {citation.get("chunk_id") for citation in citations}
        selected_ids = [chunk_id for chunk_id in (result.get("citation_chunk_ids") or []) if chunk_id in allowed_ids]
        confidence = str(result.get("confidence", "medium")).lower()
        if confidence not in {"low", "medium", "high"}:
            confidence = "medium"

        if not self._validate_llm_structure(result):
            return None

        intent = detect_question_intent(question)
        direct_score = direct_answer_score(question, answer)
        question_coverage = keyword_coverage_score(question, answer)
        if intent in {"quantity", "authority"} and (direct_score < 1.0 or question_coverage < 0.4):
            return None
        if intent == "yes_no" and (direct_score < 0.5 or question_coverage < 0.2):
            return None

        draft_conclusion = self._extract_conclusion_from_answer(draft_answer)
        if draft_conclusion:
            draft_alignment = max(
                keyword_coverage_score(draft_conclusion, answer),
                keyword_coverage_score(answer, draft_conclusion),
            )
            if draft_alignment < 0.35:
                return None

        evidence_pool = " ".join(chunk.get("text", "") for chunk in evidence_chunks[:3])
        if draft_conclusion:
            evidence_alignment = max(
                keyword_coverage_score(answer, evidence_pool),
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
            "answer": answer,
            "conclusion": answer,
            "confidence": confidence,
            "reason": str(result.get("reason", "ok")),
            "citation_chunk_ids": selected_ids,
            "notes": notes,
            "legal_basis": self._normalize_lines(result.get("legal_basis")),
            "reasoning": str(result.get("reasoning") or " ".join(self._normalize_lines(result.get("application"))) or "").strip(),
            "conditions": self._normalize_lines(result.get("conditions")),
            "application": self._normalize_lines(result.get("application")),
            "missing_info": self._normalize_lines(result.get("missing_info")),
            "structured_answer": str(result.get("structured_answer", "")).strip(),
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
            notes.append("Khong co them thong tin can bo sung.")
        structured_answer = str(llm_result.get("structured_answer", "")).strip()
        if structured_answer:
            return self._inject_citations_into_structured_answer(
                structured_answer,
                citations=citations,
                quotes=quotes,
                notes=notes,
            )
        return "\n".join(
            [
                "Can cu phap ly:",
                *[f"- {item}" for item in self._safe_lines(llm_result.get("legal_basis")) or [self._format_citation_line(citations[0]) if citations else "Chua du can cu phap ly phu hop trong corpus hien co."]],
                "",
                "Dieu kien phap ly lien quan:",
                *[f"- {item}" for item in self._safe_lines(llm_result.get("conditions")) or ["Chua xac dinh du dieu kien phap ly ro rang."]],
                "",
                "Ap dung vao tinh huong:",
                *[f"- {item}" for item in self._safe_lines(llm_result.get("application")) or ["Chua du du lieu de ap dung vao tinh huong cu the."]],
                "",
                "Ket luan:",
                f"- {str(llm_result.get('conclusion', '')).strip() or 'Toi khong biet.'}",
                "",
                "Thong tin con thieu:",
                *[f"- {note}" for note in notes],
                "",
                "Trich dan:",
                *[f'- "{quote.get("text", "")}"' for quote in quotes[:2]],
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

    def _build_conditions_lines(self, question: str, evidence_chunks: list[dict], citations: list[dict]) -> list[str]:
        lines: list[str] = []
        intent = detect_question_intent(question)
        if intent == "quantity":
            lines.append("Phai xac dinh duoc so lieu, muc huong hoac thoi han tu can cu phap ly.")
        elif intent == "authority":
            lines.append("Phai xac dinh dung chu the/co quan co tham quyen trong van ban duoc trich dan.")
        elif intent == "yes_no":
            lines.append("Phai xac dinh co hay khong thoa dieu kien neu evidence du ro.")
        else:
            lines.append("Phai doi chieu dieu kien trong van ban voi tinh huong cu the cua cau hoi.")
        if citations:
            lines.append(f"Uu tien doi chieu can cu tu {citations[0].get('label') or 'van ban phap ly chinh'}.")
        if evidence_chunks:
            lines.append("Chi duoc ket luan dua tren evidence co trong top-k da truy van.")
        return lines

    def _build_application_lines(self, question: str, supporting_sentences: list[str], confidence: str) -> list[str]:
        lines: list[str] = []
        if supporting_sentences:
            lines.append(self._join_sentences(supporting_sentences[:2]))
        else:
            lines.append("Chua co cau truc evidence du manh de ap dung truc tiep.")
        if confidence != "high":
            lines.append("Muc do chac chan chua cao, can doi chieu them toan van dieu khoan goc.")
        else:
            lines.append("Co the ap dung truc tiep vao tinh huong neu khong co tinh tiet ngoai le.")
        return lines

    def _validate_llm_structure(self, result: dict) -> bool:
        if not str(result.get("answer") or result.get("conclusion") or "").strip():
            return False
        if not self._safe_lines(result.get("legal_basis")):
            return False
        if not (str(result.get("reasoning", "")).strip() or self._safe_lines(result.get("application"))):
            return False
        if not self._safe_lines(result.get("missing_info")):
            return False
        return True

    def _safe_lines(self, value: object) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            lines = [line.strip("- ").strip() for line in value.splitlines()]
            return [line for line in lines if line]
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        return [str(value).strip()] if str(value).strip() else []

    def _normalize_lines(self, value: object) -> list[str]:
        lines = self._safe_lines(value)
        return [line for line in lines if line]

    def _inject_citations_into_structured_answer(
        self,
        structured_answer: str,
        citations: list[dict],
        quotes: list[dict],
        notes: list[str],
    ) -> str:
        citation_lines = [self._format_citation_line(item) for item in citations[:2]]
        quote_lines = [f'- "{quote.get("text", "")}"' for quote in quotes[:2]]
        has_citation_marker = any(marker in structured_answer for marker in ("[", "Dieu ", "Khoan ", "Can cu phap ly"))
        citation_block = "\n".join(f"- {line}" for line in citation_lines) if citation_lines else '- Chua du can cu phap ly phu hop trong corpus hien co.'
        if "Can cu phap ly:" not in structured_answer:
            structured_answer = "\n".join(
                [
                    "Can cu phap ly:",
                    citation_block,
                    "",
                    structured_answer.strip(),
                ]
            ).strip()
        elif not has_citation_marker:
            structured_answer = structured_answer.rstrip() + "\n\nCan cu phap ly:\n" + citation_block
        if "Thong tin con thieu:" not in structured_answer:
            structured_answer += "\n\nThong tin con thieu:\n" + "\n".join(f"- {note}" for note in notes)
        if "Trich dan:" not in structured_answer:
            structured_answer += "\n\nTrich dan:\n" + "\n".join(quote_lines or ['- "Khong co doan evidence du manh de trich dan truc tiep."'])
        return structured_answer.strip()
