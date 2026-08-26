from __future__ import annotations

from types import SimpleNamespace

from scripts.run_paper_experiments import _search_variant


class DummyPipeline:
    def __init__(self):
        self.similar_calls = []
        self.heuristic_calls = []
        self.model_calls = []
        retriever = SimpleNamespace(similar_questions=self._similar_questions)
        self.artifacts = SimpleNamespace(retriever=retriever)
        self.model_reranker = SimpleNamespace(rerank=self._model_rerank)

    def _similar_questions(self, question, top_k):
        self.similar_calls.append((question, top_k))
        return [{"qid": "q1", "qa_score": 0.9}]

    def _heuristic_retrieval(self, question, similar_questions, top_k):
        self.heuristic_calls.append((question, similar_questions, top_k))
        return [{"chunk_id": "c1", "cid": "1"}]

    def _model_rerank(self, question, candidates, top_k):
        self.model_calls.append((question, candidates, top_k))
        return candidates[:top_k]


def test_hybrid_with_qa_memory_uses_similar_questions_and_heuristic_reranker():
    pipeline = DummyPipeline()

    results = _search_variant(pipeline, "hybrid_with_qa_memory", "legal question", top_k=5)

    assert results == [{"chunk_id": "c1", "cid": "1"}]
    assert pipeline.similar_calls == [("legal question", 5)]
    assert pipeline.heuristic_calls == [
        ("legal question", [{"qid": "q1", "qa_score": 0.9}], 5)
    ]
    assert pipeline.model_calls == []


def test_cross_encoder_receives_hybrid_qa_memory_candidates():
    pipeline = DummyPipeline()

    _search_variant(pipeline, "full_with_cross_encoder_reranker", "legal question", top_k=5)

    assert pipeline.similar_calls == [("legal question", 5)]
    assert pipeline.heuristic_calls == [
        ("legal question", [{"qid": "q1", "qa_score": 0.9}], 50)
    ]
    assert pipeline.model_calls == [
        ("legal question", [{"chunk_id": "c1", "cid": "1"}], 5)
    ]


def test_hybrid_without_qa_memory_does_not_search_similar_questions():
    pipeline = DummyPipeline()

    _search_variant(pipeline, "hybrid_no_qa_memory", "legal question", top_k=5)

    assert pipeline.similar_calls == []
    assert pipeline.heuristic_calls == [("legal question", [], 5)]
