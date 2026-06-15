from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pyarrow.parquet as pq
from scipy.sparse import load_npz, save_npz, vstack
from sklearn.feature_extraction.text import HashingVectorizer

from src.data.load_qa import load_qa_records, parse_cids, parse_context_list
from src.preprocessing.chunker import build_chunks_from_corpus
from src.preprocessing.legal_metadata import CANONICAL_FIELD_ALIASES
from src.utils.io import ensure_dir, load_json, load_jsonl, save_json, save_jsonl
from src.utils.text import expand_query, keyword_text


@dataclass
class ArtifactPaths:
    processed_dir: Path = Path("data/processed")
    aligned_dir: Path = Path("data/aligned")
    indexes_dir: Path = Path("data/indexes")
    chunks_meta_path: Path = Path("data/processed/chunks_v3.jsonl")
    qa_meta_path: Path = Path("data/processed/qa_memory_v3.jsonl")
    corpus_word_path: Path = Path("data/indexes/corpus_word_v3.npz")
    corpus_char_path: Path = Path("data/indexes/corpus_char_v3.npz")
    qa_path: Path = Path("data/indexes/qa_questions_v3.npz")
    manifest_path: Path = Path("data/indexes/manifest_v3.json")


class IndexedArtifactStore:
    def __init__(self, paths: ArtifactPaths | None = None):
        self.paths = paths or ArtifactPaths()
        self.manifest = load_json(self.paths.manifest_path)
        self.corpus_meta = load_jsonl(self.paths.chunks_meta_path)
        self.qa_meta = load_jsonl(self.paths.qa_meta_path)
        self.corpus_word_matrix = load_npz(self.paths.corpus_word_path)
        self.corpus_char_matrix = load_npz(self.paths.corpus_char_path)
        self.qa_question_matrix = load_npz(self.paths.qa_path)
        self.word_vectorizer = build_word_vectorizer()
        self.char_vectorizer = build_char_vectorizer()
        self.qa_vectorizer = build_question_vectorizer()
        self._cid_to_row_ids: dict[str, list[int]] = {}
        for item in self.corpus_meta:
            self._cid_to_row_ids.setdefault(str(item["cid"]), []).append(int(item["row_id"]))

    def fetch_chunk_texts(self, row_ids: list[int]) -> dict[int, str]:
        return {
            row_id: str(self.corpus_meta[row_id].get("text", ""))
            for row_id in row_ids
            if 0 <= row_id < len(self.corpus_meta)
        }

    def fetch_chunks_by_cids(self, cids: list[str], limit_per_cid: int = 2) -> list[dict]:
        chunks: list[dict] = []
        for cid in cids:
            row_ids = self._cid_to_row_ids.get(str(cid), [])
            for row_id in row_ids[:limit_per_cid]:
                chunks.append({**self.corpus_meta[row_id]})
        return chunks


def build_word_vectorizer() -> HashingVectorizer:
    return HashingVectorizer(
        n_features=2**18,
        alternate_sign=False,
        norm="l2",
        lowercase=True,
        ngram_range=(1, 2),
        preprocessor=expand_query,
        tokenizer=str.split,
        token_pattern=None,
    )


def build_char_vectorizer() -> HashingVectorizer:
    return HashingVectorizer(
        analyzer="char_wb",
        n_features=2**18,
        alternate_sign=False,
        norm="l2",
        ngram_range=(3, 5),
        preprocessor=keyword_text,
        lowercase=False,
    )


def build_question_vectorizer() -> HashingVectorizer:
    return HashingVectorizer(
        n_features=2**17,
        alternate_sign=False,
        norm="l2",
        lowercase=True,
        ngram_range=(1, 2),
        preprocessor=expand_query,
        tokenizer=str.split,
        token_pattern=None,
    )


def artifacts_exist(paths: ArtifactPaths | None = None) -> bool:
    active_paths = paths or ArtifactPaths()
    required = [
        active_paths.chunks_meta_path,
        active_paths.qa_meta_path,
        active_paths.corpus_word_path,
        active_paths.corpus_char_path,
        active_paths.qa_path,
        active_paths.manifest_path,
    ]
    return all(path.exists() for path in required)


def build_full_artifacts(
    corpus_path: str = "data/corpus.parquet",
    train_path: str = "data/train.parquet",
    force: bool = False,
    max_chunks: int | None = None,
    paths: ArtifactPaths | None = None,
) -> dict:
    active_paths = paths or ArtifactPaths()
    ensure_dir(active_paths.processed_dir)
    ensure_dir(active_paths.aligned_dir)
    ensure_dir(active_paths.indexes_dir)

    if max_chunks is None:
        env_limit = int(os.getenv("LEGAL_QA_MAX_CHUNKS", "0") or "0")
        max_chunks = env_limit if env_limit > 0 else None

    if not force and artifacts_exist(active_paths):
        return load_json(active_paths.manifest_path)

    word_vectorizer = build_word_vectorizer()
    char_vectorizer = build_char_vectorizer()
    qa_vectorizer = build_question_vectorizer()

    corpus_word_parts = []
    corpus_char_parts = []
    chunks_meta: list[dict] = []

    parquet_file = pq.ParquetFile(corpus_path)
    requested_columns = _resolve_requested_columns(set(parquet_file.schema.names))
    total_chunks = 0
    row_id = 0
    for batch in parquet_file.iter_batches(columns=requested_columns, batch_size=2048):
        records = batch.to_pylist()
        built_chunks = build_chunks_from_corpus(records)
        if max_chunks:
            remaining = max_chunks - total_chunks
            if remaining <= 0:
                break
            built_chunks = built_chunks[:remaining]
        if not built_chunks:
            continue

        texts = [chunk["text"] for chunk in built_chunks]
        corpus_word_parts.append(word_vectorizer.transform(keyword_text(text) for text in texts))
        corpus_char_parts.append(char_vectorizer.transform(texts))

        for chunk in built_chunks:
            meta = {
                "row_id": row_id,
                "chunk_id": chunk["chunk_id"],
                "cid": str(chunk["cid"]),
                "title": chunk.get("title"),
                "doc_name": chunk.get("doc_name"),
                "doc_number": chunk.get("doc_number"),
                "chapter": chunk.get("chapter"),
                "article": chunk.get("article"),
                "clause": chunk.get("clause"),
                "issued_date": chunk.get("issued_date"),
                "effective_date": chunk.get("effective_date"),
                "expiry_date": chunk.get("expiry_date"),
                "validity_status": chunk.get("validity_status"),
                "source_path": chunk.get("source_path"),
                "source_type": chunk.get("source_type"),
                "chunk_level": chunk.get("chunk_level", "article"),
                "token_len": int(chunk.get("token_len", 0)),
                "text": chunk["text"],
            }
            chunks_meta.append(meta)
            row_id += 1
        total_chunks += len(built_chunks)

    if not chunks_meta:
        raise RuntimeError("No corpus chunks were built from corpus.parquet")

    save_npz(active_paths.corpus_word_path, vstack(corpus_word_parts))
    save_npz(active_paths.corpus_char_path, vstack(corpus_char_parts))
    save_jsonl(active_paths.chunks_meta_path, chunks_meta)

    qa_records = load_qa_records(train_path)
    qa_meta = []
    qa_texts = []
    for record in qa_records:
        meta = {
            "qid": str(record.get("qid", "")),
            "question": str(record.get("question", "")),
            "cids": parse_cids(record.get("cid")),
            "contexts": parse_context_list(record.get("context_list")),
        }
        if not meta["question"] or not meta["cids"]:
            continue
        qa_meta.append(meta)
        qa_texts.append(keyword_text(meta["question"]))

    if not qa_meta:
        raise RuntimeError("No QA memory records were built from train.parquet")

    save_npz(active_paths.qa_path, qa_vectorizer.transform(qa_texts))
    save_jsonl(active_paths.qa_meta_path, qa_meta)

    manifest = {
        "version": 2,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "corpus_chunks": len(chunks_meta),
        "qa_memory_records": len(qa_meta),
        "corpus_path": corpus_path,
        "train_path": train_path,
        "max_chunks": max_chunks or 0,
    }
    save_json(active_paths.manifest_path, manifest)
    return manifest


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
