"""
Reranking strategies for legal document ranking.

Provides heuristic-based reranking and optional cross-encoder model reranking
to improve answer relevance and ranking quality.
"""

from __future__ import annotations

from src.utils.text import (
    important_query_phrases,
    important_query_terms,
    keyword_coverage_score,
    phrase_coverage_score,
    tokenize,
)


class HeuristicReranker:
    """
    Rerank documents using heuristic scoring without ML models.

    Scoring factors:
    - Keyword overlap density
    - Legal document boosting (articles/clauses)
    - Keyword coverage and phrase matching
    - Query term frequency in documents
    """

    def rerank(self, query: str, candidates: list[dict], top_k: int = 5) -> list[dict]:
        """
        Rerank candidates using heuristic scoring.

        Args:
            query: Legal question
            candidates: List of candidate documents with scores
            top_k: Number of documents to return

        Returns:
            Reranked list of top_k documents
        """
        query_tokens = set(tokenize(query))
        query_keywords = important_query_terms(query)
        query_phrases = important_query_phrases(query)
        reranked: list[dict] = []

        for candidate in candidates:
            text = candidate.get("text", "")
            lowered = " ".join(tokenize(text))
            passage_tokens = tokenize(text)
            overlap = len(query_tokens.intersection(passage_tokens))
            density = overlap / max(len(set(passage_tokens)), 1)
            legal_boost = 0.15 if candidate.get("article") else 0.0
            coverage = keyword_coverage_score(query, text)
            phrase_coverage = phrase_coverage_score(query, text)
            exact_keyword_bonus = sum(0.2 for keyword in query_keywords if keyword in lowered)
            exact_phrase_bonus = sum(0.8 for phrase in query_phrases if phrase in lowered)
            score = (
                float(candidate.get("hybrid_score", 0.0))
                + overlap
                + density
                + legal_boost
                + (coverage * 2.5)
                + (phrase_coverage * 4.5)
                + exact_keyword_bonus
                + exact_phrase_bonus
            )
            reranked.append(
                {
                    **candidate,
                    "rerank_score": round(score, 6),
                    "keyword_coverage": round(coverage, 4),
                    "phrase_coverage": round(phrase_coverage, 4),
                }
            )

        reranked.sort(key=lambda item: item["rerank_score"], reverse=True)
        return reranked[:top_k]
