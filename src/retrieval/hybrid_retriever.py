"""
Hybrid retrieval combining BM25 (sparse) and dense embeddings.

Implements a two-stage retrieval pipeline that merges results from
multiple sources with dynamic boosting based on query analysis and
QA memory similarity.
"""

from __future__ import annotations

from collections import defaultdict

from src.indexing.artifacts import IndexedArtifactStore
from src.retrieval.bm25_retriever import BM25Retriever, top_sparse_scores
from src.retrieval.dense_retriever import DenseRetriever
from src.retrieval.model_retriever import OptionalEmbeddingRetriever
from src.utils.text import expand_query, keyword_text


class HybridRetriever:
    """
    Hybrid retriever combining sparse (BM25) and dense (embedding) search.

    Features:
    - Multi-source retrieval with dynamic score merging
    - Query expansion for better recall
    - QA memory similarity boosting
    - Article-level relevance boosting
    - Configurable per-source depth for efficiency
    """
    def __init__(self, store: IndexedArtifactStore, retriever_model_path: str = "models/retriever-best"):
        """
        Initialize hybrid retriever.

        Args:
            store: Artifact store with indexed data
            retriever_model_path: Path to embedding model for optional dense retrieval
        """
        self.store = store
        self.bm25 = BM25Retriever(store)
        self.dense = DenseRetriever(store)
        self.embedding_retriever = OptionalEmbeddingRetriever(model_path=retriever_model_path)

    def search(self, query: str, top_k: int = 10, per_source_k: int = 30) -> list[dict]:
        """
        Search for relevant legal documents using hybrid approach.

        Combines BM25 (sparse) and dense embedding search with query expansion
        and QA memory boosting for better recall and precision.

        Args:
            query: Legal question in Vietnamese
            top_k: Number of final results to return
            per_source_k: Number of candidates to fetch from each source

        Returns:
            List of ranked documents with scores and metadata
        """
        expanded_query = expand_query(query)
        bm25_hits = self.bm25.search(expanded_query, top_k=per_source_k)
        dense_hits = self.dense.search(expanded_query, top_k=per_source_k)
        qa_hits = self._search_similar_questions(expanded_query, top_k=8)

        cid_boosts: dict[str, float] = defaultdict(float)
        for hit in qa_hits:
            for cid in hit["cids"]:
                cid_boosts[str(cid)] += hit["qa_score"]

        merged: dict[str, dict] = {}
        rank_bonus = defaultdict(float)

        for rank, item in enumerate(bm25_hits, start=1):
            key = item["chunk_id"]
            merged[key] = {**item}
            rank_bonus[key] += 1.0 / rank

        for rank, item in enumerate(dense_hits, start=1):
            key = item["chunk_id"]
            current = merged.get(key, {})
            merged[key] = {**current, **item}
            rank_bonus[key] += 1.0 / rank

        results = []
        for key, item in merged.items():
            bm25_score = float(item.get("bm25_score", 0.0))
            dense_score = float(item.get("dense_score", 0.0))
            qa_boost = float(cid_boosts.get(str(item["cid"]), 0.0))
            fused = (
                (0.5 * bm25_score)
                + (0.3 * dense_score)
                + (0.35 * rank_bonus[key])
                + (0.8 * qa_boost)
            )
            results.append(
                {
                    **item,
                    "qa_boost": round(qa_boost, 6),
                    "hybrid_score": round(fused, 6),
                }
            )

        results.sort(key=lambda item: item["hybrid_score"], reverse=True)
        top_results = results[:top_k]
        texts = self.store.fetch_chunk_texts([int(item["row_id"]) for item in top_results])
        for item in top_results:
            item["text"] = texts.get(int(item["row_id"]), "")
        top_results = self.embedding_retriever.score_candidates(query, top_results)
        return top_results[:top_k]

    def similar_questions(self, query: str, top_k: int = 5) -> list[dict]:
        return self._search_similar_questions(query, top_k=top_k)

    def _search_similar_questions(self, query: str, top_k: int = 5) -> list[dict]:
        vector = self.store.qa_vectorizer.transform([keyword_text(query)])
        hits = top_sparse_scores(self.store.qa_question_matrix, vector, top_k=top_k)
        return [
            {
                **self.store.qa_meta[row_id],
                "qa_score": round(score, 6),
            }
            for row_id, score in hits
        ]
