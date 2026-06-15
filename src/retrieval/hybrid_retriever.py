"""
Hybrid retrieval combining BM25 (sparse) and dense embeddings.

Implements a two-stage retrieval pipeline that merges results from
multiple sources with dynamic boosting based on query analysis and
QA memory similarity.
"""

from __future__ import annotations

from collections import defaultdict

from src.indexing.artifacts import IndexedArtifactStore
from src.retrieval.elasticsearch_retriever import OptionalElasticsearchRetriever
from src.retrieval.embedding_ensemble import OptionalEmbeddingEnsembler
from src.retrieval.bm25_retriever import BM25Retriever, top_sparse_scores
from src.retrieval.dense_retriever import DenseRetriever
from src.retrieval.model_retriever import OptionalEmbeddingRetriever
from src.utils.io import load_json
from src.utils.text import (
    direct_answer_score,
    expand_query,
    keyword_coverage_score,
    keyword_text,
    phrase_coverage_score,
    procedural_noise_score,
)


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
    def __init__(
        self,
        store: IndexedArtifactStore,
        retriever_model_path: str = "models/retriever-best",
        retrieval_config_path: str = "configs/serving/retrieval.hybrid.json",
    ):
        """
        Initialize hybrid retriever.

        Args:
            store: Artifact store with indexed data
            retriever_model_path: Path to embedding model for optional dense retrieval
        """
        self.store = store
        self.config = load_json(retrieval_config_path)
        self.weights = self.config.get("merge_weights") or {}
        self.qa_config = self.config.get("qa_memory") or {}
        self.bm25 = BM25Retriever(store)
        self.dense = DenseRetriever(store)
        self.embedding_retriever = OptionalEmbeddingRetriever(model_path=retriever_model_path)
        self.embedding_ensemble = OptionalEmbeddingEnsembler(self.config.get("embedding_models") or [])
        self.elasticsearch = OptionalElasticsearchRetriever(self.config.get("elasticsearch") or {})

    def search(self, query: str, top_k: int = 10, per_source_k: int = 120) -> list[dict]:
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
        per_source_k = int(per_source_k or self.config.get("per_source_k", 120))
        bm25_hits = self.bm25.search(expanded_query, top_k=per_source_k)
        dense_hits = self.dense.search(expanded_query, top_k=per_source_k)
        es_top_k = min(per_source_k, int((self.config.get("elasticsearch") or {}).get("top_k", 60)))
        es_hits = self.elasticsearch.search(expanded_query, top_k=es_top_k)
        qa_hits = self._search_similar_questions(expanded_query, top_k=int(self.qa_config.get("top_k", 12)))

        cid_boosts: dict[str, float] = defaultdict(float)
        for hit in qa_hits:
            for cid in hit["cids"]:
                cid_boosts[str(cid)] = max(float(hit["qa_score"]), cid_boosts[str(cid)])

        merged: dict[str, dict] = {}
        rank_bonus = defaultdict(float)

        for rank, item in enumerate(bm25_hits, start=1):
            key = item["chunk_id"]
            merged[key] = {**item, "sources": ["bm25"]}
            rank_bonus[key] += 1.0 / rank

        for rank, item in enumerate(dense_hits, start=1):
            key = item["chunk_id"]
            current = merged.get(key, {})
            merged[key] = {**current, **item, "sources": sorted(set((current.get("sources") or []) + ["char-dense"]))}
            rank_bonus[key] += 1.0 / rank

        for rank, item in enumerate(es_hits, start=1):
            key = item["chunk_id"]
            current = merged.get(key, {})
            merged[key] = {**current, **item, "sources": sorted(set((current.get("sources") or []) + ["elasticsearch"]))}
            rank_bonus[key] += 1.0 / rank

        # When QA memory strongly suggests a CID, pull a few matching corpus chunks
        # into the candidate set even if lexical retrieval missed them.
        qa_seed_cids = [
            str(cid)
            for hit in qa_hits[: int(self.qa_config.get("seed_top_hits", 6))]
            if float(hit.get("qa_score", 0.0)) >= float(self.qa_config.get("seed_score_threshold", 0.6))
            for cid in (hit.get("cids") or [])[: int(self.qa_config.get("seed_cids_per_hit", 2))]
        ]
        for item in self.store.fetch_chunks_by_cids(
            qa_seed_cids,
            limit_per_cid=int(self.qa_config.get("seed_chunks_per_cid", 2)),
        ):
            key = item["chunk_id"]
            current = merged.get(key, {})
            merged[key] = {**item, **current, "sources": sorted(set((current.get("sources") or []) + ["qa-cid-seed"]))}

        results = []
        for key, item in merged.items():
            bm25_score = float(item.get("bm25_score", 0.0))
            dense_score = float(item.get("dense_score", 0.0))
            es_score = float(item.get("es_score", 0.0))
            coverage = keyword_coverage_score(query, item.get("text", ""))
            phrase_coverage = phrase_coverage_score(query, item.get("text", ""))
            direct_score = direct_answer_score(query, item.get("text", ""))
            procedural_noise = procedural_noise_score(item.get("text", ""))
            raw_qa_boost = float(cid_boosts.get(str(item["cid"]), 0.0))
            qa_boost = raw_qa_boost * (0.25 + (0.55 * coverage) + (0.7 * phrase_coverage))
            fused = (
                (float(self.weights.get("bm25", 0.5)) * bm25_score)
                + (float(self.weights.get("dense", 0.3)) * dense_score)
                + (float(self.weights.get("elasticsearch", 0.15)) * es_score)
                + (float(self.weights.get("rank_bonus", 0.35)) * rank_bonus[key])
                + (float(self.weights.get("keyword_coverage", 0.2)) * coverage)
                + (float(self.weights.get("phrase_coverage", 0.35)) * phrase_coverage)
                + (float(self.weights.get("direct_answer", 0.6)) * direct_score)
                + (float(self.weights.get("qa_boost", 0.8)) * qa_boost)
                - (float(self.weights.get("procedural_noise_penalty", 0.15)) * procedural_noise)
            )
            results.append(
                {
                    **item,
                    "qa_boost": round(qa_boost, 6),
                    "es_score": round(es_score, 6),
                    "keyword_coverage": round(coverage, 4),
                    "phrase_coverage": round(phrase_coverage, 4),
                    "direct_answer_score": round(direct_score, 4),
                    "procedural_noise": round(procedural_noise, 4),
                    "hybrid_score": round(fused, 6),
                    "sources": item.get("sources") or ["bm25"],
                }
            )

        results.sort(key=lambda item: item["hybrid_score"], reverse=True)
        preselect_k = max(
            top_k * int(self.config.get("preselect_multiplier", 8)),
            int(self.config.get("preselect_min", 80)),
        )
        top_results = results[:preselect_k]
        texts = self.store.fetch_chunk_texts([int(item["row_id"]) for item in top_results])
        for item in top_results:
            item["text"] = texts.get(int(item["row_id"]), "")
        top_results = self.embedding_retriever.score_candidates(query, top_results)
        top_results = self.embedding_ensemble.score_candidates(query, top_results)
        top_results = self._limit_chunks_per_cid(
            top_results,
            top_k=top_k,
            max_chunks_per_cid=int(self.config.get("max_chunks_per_cid", 1)),
        )
        return top_results[:top_k]

    def similar_questions(self, query: str, top_k: int = 5) -> list[dict]:
        return self._search_similar_questions(query, top_k=top_k)

    def _limit_chunks_per_cid(self, items: list[dict], top_k: int, max_chunks_per_cid: int = 1) -> list[dict]:
        limited: list[dict] = []
        counts: dict[str, int] = defaultdict(int)
        for item in items:
            cid = str(item.get("cid"))
            if counts[cid] >= max_chunks_per_cid:
                continue
            counts[cid] += 1
            limited.append(item)
            if len(limited) >= top_k:
                break
        return limited

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
