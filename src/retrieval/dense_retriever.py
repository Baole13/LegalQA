from __future__ import annotations

from src.indexing.artifacts import IndexedArtifactStore
from src.retrieval.bm25_retriever import top_sparse_scores


class DenseRetriever:
    def __init__(self, store: IndexedArtifactStore):
        self.store = store

    def search(self, query: str, top_k: int = 10) -> list[dict]:
        vector = self.store.char_vectorizer.transform([query])
        hits = top_sparse_scores(self.store.corpus_char_matrix, vector, top_k=top_k)
        return [
            {
                **self.store.corpus_meta[row_id],
                "dense_score": round(score, 6),
            }
            for row_id, score in hits
        ]
