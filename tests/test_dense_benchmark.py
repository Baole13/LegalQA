from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

import scripts.run_paper_experiments as experiments
from src.retrieval.faiss_dense_retriever import DenseIndexUnavailableError, OptionalFaissDenseRetriever


class FakeDenseIndex:
    def search(self, query_vector, top_k):
        assert query_vector.dtype == np.float32
        return np.asarray([[0.9, 0.5]], dtype=np.float32), np.asarray([[1, 0]], dtype=np.int64)


class FakeEmbeddingModel:
    def encode(self, texts, **kwargs):
        assert kwargs["normalize_embeddings"] is True
        return np.asarray([[1.0, 0.0]], dtype=np.float32)


def test_dense_search_maps_faiss_positions_to_corpus_rows():
    retriever = OptionalFaissDenseRetriever.__new__(OptionalFaissDenseRetriever)
    retriever.index = FakeDenseIndex()
    retriever.row_ids = np.asarray([2, 0], dtype=np.int64)
    retriever.model = FakeEmbeddingModel()
    retriever.store = SimpleNamespace(
        corpus_meta=[
            {"row_id": 0, "chunk_id": "c0", "text": "zero"},
            {"row_id": 1, "chunk_id": "c1", "text": "one"},
            {"row_id": 2, "chunk_id": "c2", "text": "two"},
        ]
    )

    results = retriever.search("query", top_k=2)

    assert [item["row_id"] for item in results] == [0, 2]
    assert results[0]["neural_dense_score"] == pytest.approx(0.9)
    assert results[0]["sources"] == ["neural-dense"]


def test_dense_metadata_rejects_mismatched_corpus_or_model():
    retriever = OptionalFaissDenseRetriever.__new__(OptionalFaissDenseRetriever)
    retriever.store = SimpleNamespace(manifest={"corpus_chunks": 2, "version": 3}, corpus_meta=[{}, {}])
    retriever.model_path = "models/retriever-best"

    with pytest.raises(ValueError, match="corpus_chunks"):
        retriever._validate_metadata(
            {"corpus_chunks": 3, "artifact_version": 3, "model_path": "models/retriever-best"}
        )
    with pytest.raises(ValueError, match="model_path"):
        retriever._validate_metadata(
            {"corpus_chunks": 2, "artifact_version": 3, "model_path": "models/other"}
        )


def test_dense_unavailable_error_contains_build_command():
    retriever = OptionalFaissDenseRetriever.__new__(OptionalFaissDenseRetriever)
    retriever.index = None
    retriever.row_ids = None
    retriever.model = None
    retriever.load_error = "missing_dense_artifacts"

    with pytest.raises(DenseIndexUnavailableError, match="build_dense_index.py"):
        retriever.ensure_available()


def test_dense_only_uses_only_neural_dense_and_heuristic_reranker():
    calls = []
    dense = SimpleNamespace(
        search=lambda question, top_k: calls.append((question, top_k))
        or [{"row_id": 0, "chunk_id": "c0", "text": "evidence", "neural_dense_score": 0.8}]
    )
    reranker = SimpleNamespace(rerank=lambda question, candidates, top_k: candidates[:top_k])
    pipeline = SimpleNamespace(
        artifacts=SimpleNamespace(retriever=SimpleNamespace(neural_dense=dense)),
        heuristic_reranker=reranker,
    )

    results = experiments._dense_only_search(pipeline, "question", top_k=1)

    assert calls == [("question", 120)]
    assert results[0]["sources"] == ["neural-dense"]
    assert results[0]["qa_boost"] == 0.0


def test_retrieval_variant_notes_describe_all_methods():
    notes = experiments._retrieval_variant_notes()
    for label in ("BM25", "Dense", "Hybrid", "Hybrid + QA-memory", "Cross-encoder reranker"):
        assert f"**{label}:**" in notes
