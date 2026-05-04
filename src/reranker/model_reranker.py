from __future__ import annotations

from pathlib import Path


class OptionalCrossEncoderReranker:
    def __init__(self, model_path: str = "models/reranker-best"):
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
            from sentence_transformers.cross_encoder import CrossEncoder
        except ImportError as exc:  # pragma: no cover
            self.load_error = f"cross_encoder_import_failed: {exc}"
            return
        try:
            self.model = CrossEncoder(str(model_dir), max_length=512)
            self.loaded = True
        except Exception as exc:  # pragma: no cover
            self.load_error = str(exc)

    def rerank(self, query: str, candidates: list[dict], top_k: int = 5) -> list[dict]:
        if not self.available() or not candidates:
            return candidates[:top_k]
        pairs = [[query, item.get("text", "")] for item in candidates]
        scores = self.model.predict(pairs)
        rescored = []
        for item, score in zip(candidates, scores):
            rescored.append({**item, "model_rerank_score": float(score), "rerank_score": float(score)})
        rescored.sort(key=lambda item: item["rerank_score"], reverse=True)
        return rescored[:top_k]
