from __future__ import annotations

from pathlib import Path

import bm25s

from src.indexing.artifacts import IndexedArtifactStore
from src.utils.text import tokenize

DEFAULT_INDEX_DIR = Path("data/indexes/bm25s_corpus_v1")


class BM25OkapiRetriever:
    """
    Real Okapi BM25 (Robertson/Sparck-Jones) over the same chunk corpus the
    hashing-based lexical retriever uses, so the paper's BM25 baseline is BM25.
    """

    def __init__(self, store: IndexedArtifactStore, index_dir: Path | str = DEFAULT_INDEX_DIR):
        self.store = store
        self.index_dir = Path(index_dir)
        if not (self.index_dir / "data.csc.index.npy").exists():
            raise FileNotFoundError(
                f"BM25 index not found at {self.index_dir}. "
                "Build it with: PYTHONPATH=. python scripts/build_bm25_index.py"
            )
        self.retriever = bm25s.BM25.load(str(self.index_dir), mmap=True)

    def search(self, query: str, top_k: int = 10) -> list[dict]:
        tokens = tokenize(query)
        if not tokens:
            return []
        limit = min(top_k, len(self.store.corpus_meta))
        row_ids, scores = self.retriever.retrieve([tokens], k=limit, show_progress=False)
        hits = []
        for row_id, score in zip(row_ids[0], scores[0]):
            if float(score) <= 0:
                continue
            hits.append(
                {
                    **self.store.corpus_meta[int(row_id)],
                    "bm25_score": round(float(score), 6),
                }
            )
        return hits


def build_index(
    store: IndexedArtifactStore,
    index_dir: Path | str = DEFAULT_INDEX_DIR,
    k1: float = 1.5,
    b: float = 0.75,
) -> dict:
    index_dir = Path(index_dir)
    corpus_tokens = [tokenize(str(item.get("text", ""))) for item in store.corpus_meta]
    retriever = bm25s.BM25(method="lucene", k1=k1, b=b)
    retriever.index(corpus_tokens, show_progress=False)
    index_dir.parent.mkdir(parents=True, exist_ok=True)
    retriever.save(str(index_dir))
    return {
        "index_dir": str(index_dir),
        "documents": len(corpus_tokens),
        "method": "lucene",
        "k1": k1,
        "b": b,
    }
