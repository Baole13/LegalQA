from __future__ import annotations

import numpy as np

from src.indexing.artifacts import IndexedArtifactStore
from src.utils.text import keyword_text


def top_sparse_scores(matrix, vector, top_k: int) -> list[tuple[int, float]]:
    scores = matrix @ vector.T
    if scores.nnz == 0:
        return []
    rows = scores.nonzero()[0]
    data = scores.data
    if len(data) <= top_k:
        order = np.argsort(data)[::-1]
    else:
        top = np.argpartition(data, -top_k)[-top_k:]
        order = top[np.argsort(data[top])[::-1]]
    return [(int(rows[pos]), float(data[pos])) for pos in order if float(data[pos]) > 0]


class BM25Retriever:
    """
    Hashing-based lexical retriever that fills the BM25 role without a fitted vocab.
    """

    def __init__(self, store: IndexedArtifactStore):
        self.store = store

    def search(self, query: str, top_k: int = 10) -> list[dict]:
        vector = self.store.word_vectorizer.transform([keyword_text(query)])
        hits = top_sparse_scores(self.store.corpus_word_matrix, vector, top_k=top_k)
        return [
            {
                **self.store.corpus_meta[row_id],
                "bm25_score": round(score, 6),
            }
            for row_id, score in hits
        ]
