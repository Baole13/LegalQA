from __future__ import annotations

from pathlib import Path

import numpy as np


class OptionalEmbeddingEnsembler:
    def __init__(self, model_configs: list[dict] | None = None):
        self.model_configs = model_configs or []
        self.models: list[dict] = []
        self.load_errors: list[str] = []
        self._lazy_load()

    def available(self) -> bool:
        return bool(self.models)

    def _lazy_load(self) -> None:
        if not self.model_configs:
            return
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:  # pragma: no cover
            self.load_errors.append(f"sentence_transformers_import_failed: {exc}")
            return

        for config in self.model_configs:
            model_path = Path(str(config.get("path", "")))
            if not model_path.exists():
                continue
            try:
                self.models.append(
                    {
                        "name": str(config.get("name", model_path.name)),
                        "weight": float(config.get("weight", 1.0)),
                        "model": SentenceTransformer(str(model_path)),
                    }
                )
            except Exception as exc:  # pragma: no cover
                self.load_errors.append(f"{model_path}: {exc}")

    def score_candidates(self, query: str, candidates: list[dict]) -> list[dict]:
        if not self.available() or not candidates:
            return candidates

        texts = [candidate.get("text", "") for candidate in candidates]
        aggregate = np.zeros(len(candidates), dtype=float)
        for item in self.models:
            model = item["model"]
            weight = float(item["weight"])
            query_embedding = model.encode([query], normalize_embeddings=True)
            passage_embeddings = model.encode(texts, normalize_embeddings=True)
            aggregate += np.dot(passage_embeddings, query_embedding[0]) * weight

        rescored = []
        for candidate, score in zip(candidates, aggregate):
            rescored.append(
                {
                    **candidate,
                    "embedding_ensemble_score": float(score),
                    "hybrid_score": float(candidate.get("hybrid_score", 0.0)) + float(score),
                }
            )
        rescored.sort(key=lambda item: item["hybrid_score"], reverse=True)
        return rescored
