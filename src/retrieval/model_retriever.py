from __future__ import annotations

from pathlib import Path

import numpy as np


class OptionalEmbeddingRetriever:
    def __init__(self, model_path: str = "models/retriever-best"):
        self.model_path = model_path
        self.loaded = False
        self.model = None
        self.load_error: str | None = None
        self._lazy_load()

    def available(self) -> bool:
        return self.loaded and self.model is not None

    def _lazy_load(self) -> None:
        model_dir = Path(self.model_path)
        if not model_dir.exists():
            self.load_error = "model_not_found"
            return
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:  # pragma: no cover
            self.load_error = f"sentence_transformers_import_failed: {exc}"
            return
        try:
            self.model = SentenceTransformer(str(model_dir))
            self.loaded = True
        except Exception as exc:  # pragma: no cover
            self.load_error = str(exc)

    def score_candidates(self, query: str, candidates: list[dict]) -> list[dict]:
        if not self.available() or not candidates:
            return candidates
        query_embedding = self.model.encode([query], normalize_embeddings=True)
        passage_embeddings = self.model.encode(
            [candidate.get("text", "") for candidate in candidates],
            normalize_embeddings=True,
        )
        scores = np.dot(passage_embeddings, query_embedding[0])
        rescored = []
        for candidate, score in zip(candidates, scores):
            embedding_score = float(score)
            rescored.append(
                {
                    **candidate,
                    "embedding_score": embedding_score,
                    "hybrid_score": float(candidate.get("hybrid_score", 0.0)) + (0.9 * embedding_score),
                }
            )
        rescored.sort(key=lambda item: item["hybrid_score"], reverse=True)
        return rescored
