from __future__ import annotations

import os
from pathlib import Path

import pyarrow.parquet as pq

from src.preprocessing.chunker import build_chunks_from_corpus
from src.preprocessing.legal_metadata import CANONICAL_FIELD_ALIASES


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
    requested_columns = _resolve_requested_columns(available_columns)
    for batch in parquet_file.iter_batches(columns=requested_columns, batch_size=2048):
        records = batch.to_pylist()
        built = build_chunks_from_corpus(records)
        chunks.extend(built)
        if chunk_limit and len(chunks) >= chunk_limit:
            return chunks[:chunk_limit]
    return chunks


def _resolve_requested_columns(available_columns: set[str]) -> list[str]:
    requested: list[str] = []
    for aliases in CANONICAL_FIELD_ALIASES.values():
        for alias in aliases:
            if alias in available_columns:
                requested.append(alias)
                break
    if "cid" not in requested:
        requested.append("cid")
    if "text" not in requested:
        requested.append("text")
    return requested
