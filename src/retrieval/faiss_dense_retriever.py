from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from src.indexing.artifacts import IndexedArtifactStore


class DenseIndexUnavailableError(RuntimeError):
    """Raised when the neural dense index cannot be used safely."""


class OptionalFaissDenseRetriever:
    def __init__(self, store: IndexedArtifactStore, model_path: str, config: dict | None = None):
        self.store = store
        self.model_path = str(model_path)
        self.config = config or {}
        self.index_path = Path(str(self.config.get("index_path", "data/indexes/corpus_dense_v1.faiss")))
        self.row_ids_path = Path(str(self.config.get("row_ids_path", "data/indexes/corpus_dense_row_ids_v1.npy")))
        self.metadata_path = Path(str(self.config.get("metadata_path", "data/indexes/corpus_dense_v1.json")))
        self.index = None
        self.row_ids: np.ndarray | None = None
        self.model = None
        self.metadata: dict = {}
        self.load_error: str | None = None
        self._load()

    def available(self) -> bool:
        return self.index is not None and self.row_ids is not None and self.model is not None

    def ensure_available(self) -> None:
        if self.available():
            return
        detail = self.load_error or "dense_index_not_loaded"
        raise DenseIndexUnavailableError(
            f"Neural dense retrieval is unavailable ({detail}). Build it with "
            "`PYTHONPATH=. python scripts/build_dense_index.py`."
        )

    def _load(self) -> None:
        missing = [path for path in (self.index_path, self.row_ids_path, self.metadata_path) if not path.exists()]
        if missing:
            self.load_error = "missing_dense_artifacts: " + ", ".join(str(path) for path in missing)
            return
        model_dir = Path(self.model_path)
        if not model_dir.exists():
            self.load_error = f"dense_model_not_found: {model_dir}"
            return
        try:
            import faiss
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:  # pragma: no cover
            self.load_error = f"dense_dependency_import_failed: {exc}"
            return
        try:
            self.metadata = json.loads(self.metadata_path.read_text(encoding="utf-8"))
            self._validate_metadata(self.metadata)
            row_ids = np.load(self.row_ids_path, allow_pickle=False)
            index = faiss.read_index(str(self.index_path))
            if index.ntotal != len(row_ids):
                raise ValueError(f"index size {index.ntotal} != row mapping size {len(row_ids)}")
            if int(self.metadata.get("dimension", -1)) != int(index.d):
                raise ValueError(f"metadata dimension {self.metadata.get('dimension')} != index dimension {index.d}")
            self.model = SentenceTransformer(self.model_path)
            model_dimension = int(self.model.get_sentence_embedding_dimension())
            if model_dimension != int(index.d):
                raise ValueError(f"model dimension {model_dimension} != index dimension {index.d}")
            self.row_ids = row_ids.astype(np.int64, copy=False)
            self.index = index
        except Exception as exc:  # pragma: no cover
            self.index = None
            self.row_ids = None
            self.model = None
            self.load_error = f"invalid_dense_index: {exc}"

    def _validate_metadata(self, metadata: dict) -> None:
        expected_chunks = int(self.store.manifest.get("corpus_chunks", len(self.store.corpus_meta)))
        if int(metadata.get("corpus_chunks", -1)) != expected_chunks:
            raise ValueError(
                f"index corpus_chunks {metadata.get('corpus_chunks')} != active corpus_chunks {expected_chunks}"
            )
        if int(metadata.get("artifact_version", -1)) != int(self.store.manifest.get("version", -1)):
            raise ValueError(
                f"index artifact_version {metadata.get('artifact_version')} != active artifact_version "
                f"{self.store.manifest.get('version')}"
            )
        indexed_model = str(metadata.get("model_path", ""))
        if Path(indexed_model).as_posix() != Path(self.model_path).as_posix():
            raise ValueError(f"index model_path {indexed_model!r} != configured model_path {self.model_path!r}")

    def search(self, query: str, top_k: int = 10) -> list[dict]:
        self.ensure_available()
        query_vector = self.model.encode(
            [query], normalize_embeddings=True, convert_to_numpy=True
        ).astype("float32", copy=False)
        scores, positions = self.index.search(query_vector, min(int(top_k), len(self.row_ids)))
        results: list[dict] = []
        for score, position in zip(scores[0], positions[0]):
            if int(position) < 0:
                continue
            row_id = int(self.row_ids[int(position)])
            results.append(
                {
                    **self.store.corpus_meta[row_id],
                    "neural_dense_score": float(score),
                    "sources": ["neural-dense"],
                }
            )
        return results
