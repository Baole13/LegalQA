from __future__ import annotations

import json
from pathlib import Path
from urllib import error, parse, request

import _bootstrap

from src.indexing.artifacts import ArtifactPaths, build_full_artifacts
from src.utils.io import load_json, load_jsonl


def http_json(method: str, url: str, payload: dict | None = None, timeout: int = 30) -> tuple[int, str]:
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = request.Request(url, data=data, headers=headers, method=method)
    try:
        with request.urlopen(req, timeout=timeout) as response:
            return response.status, response.read().decode("utf-8")
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return exc.code, body


def bulk_upload(base_url: str, actions: list[str], timeout: int = 60) -> tuple[int, str]:
    payload = ("\n".join(actions) + "\n").encode("utf-8")
    req = request.Request(
        f"{base_url}/_bulk",
        data=payload,
        headers={"Content-Type": "application/x-ndjson"},
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=timeout) as response:
            return response.status, response.read().decode("utf-8")
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return exc.code, body


def main() -> None:
    retrieval_config = load_json("configs/serving/retrieval.hybrid.json")
    es_config = retrieval_config.get("elasticsearch") or {}
    if not es_config.get("enabled", False):
        print("Elasticsearch is disabled in configs/serving/retrieval.hybrid.json")
        print("Set elasticsearch.enabled=true before indexing.")
        return

    base_url = str(es_config.get("url", "http://localhost:9200")).rstrip("/")
    index_name = str(es_config.get("index", "legalqa_chunks"))
    timeout_seconds = int(es_config.get("timeout_seconds", 5))

    paths = ArtifactPaths()
    if not paths.chunks_meta_path.exists():
        manifest = build_full_artifacts(force=False)
        print(f"Artifacts ready: {manifest['corpus_chunks']} chunks")

    chunks = load_jsonl(paths.chunks_meta_path)
    print(f"Preparing {len(chunks)} chunks for Elasticsearch index '{index_name}'")

    mappings = {
        "settings": {
            "number_of_shards": 1,
            "number_of_replicas": 0,
        },
        "mappings": {
            "properties": {
                "row_id": {"type": "integer"},
                "chunk_id": {"type": "keyword"},
                "cid": {"type": "keyword"},
                "title": {"type": "text"},
                "article": {"type": "keyword"},
                "clause": {"type": "keyword"},
                "token_len": {"type": "integer"},
                "text": {"type": "text"},
            }
        },
    }

    index_url = f"{base_url}/{parse.quote(index_name)}"
    status, body = http_json("PUT", index_url, mappings, timeout=timeout_seconds)
    if status not in {200, 201} and "resource_already_exists_exception" not in body:
        raise SystemExit(f"Failed to create index: {status} {body}")

    batch_size = 1000
    for start in range(0, len(chunks), batch_size):
        batch = chunks[start : start + batch_size]
        actions: list[str] = []
        for item in batch:
            actions.append(json.dumps({"index": {"_index": index_name, "_id": item["chunk_id"]}}, ensure_ascii=False))
            actions.append(json.dumps(item, ensure_ascii=False))
        status, body = bulk_upload(base_url, actions, timeout=max(timeout_seconds, 60))
        if status not in {200, 201}:
            raise SystemExit(f"Bulk upload failed at batch {start}: {status} {body[:500]}")
        print(f"Indexed {min(start + batch_size, len(chunks))}/{len(chunks)} chunks")

    refresh_status, refresh_body = http_json("POST", f"{index_url}/_refresh", timeout=timeout_seconds)
    if refresh_status not in {200, 201}:
        raise SystemExit(f"Refresh failed: {refresh_status} {refresh_body}")
    print(f"Elasticsearch index '{index_name}' is ready.")


if __name__ == "__main__":
    main()
