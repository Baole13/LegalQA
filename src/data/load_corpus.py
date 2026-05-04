from __future__ import annotations

import os
from pathlib import Path

import pyarrow.parquet as pq

from src.preprocessing.chunker import build_chunks_from_corpus


def load_corpus_chunks(path: str | Path = "data/corpus.parquet", limit: int | None = None) -> list[dict]:
    parquet_file = pq.ParquetFile(path)
    available_columns = set(parquet_file.schema.names)
    expected = {"cid", "text"}
    missing = expected - available_columns
    if missing:
        raise ValueError(f"Corpus missing columns: {sorted(missing)}")

    chunk_limit = limit
    if chunk_limit is None:
        chunk_limit = int(os.getenv("LEGAL_QA_MAX_CHUNKS", "12000") or "12000")

    chunks: list[dict] = []
    for batch in parquet_file.iter_batches(columns=["cid", "text"], batch_size=2048):
        records = batch.to_pylist()
        built = build_chunks_from_corpus(records)
        chunks.extend(built)
        if chunk_limit and len(chunks) >= chunk_limit:
            return chunks[:chunk_limit]
    return chunks
