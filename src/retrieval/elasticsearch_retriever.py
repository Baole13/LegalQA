from __future__ import annotations

import json
from urllib import error, parse, request


class OptionalElasticsearchRetriever:
    def __init__(self, config: dict | None = None):
        self.config = config or {}
        self.enabled = bool(self.config.get("enabled", False))
        self.url = str(self.config.get("url", "http://localhost:9200")).rstrip("/")
        self.index = str(self.config.get("index", "legalqa_chunks"))
        self.top_k = int(self.config.get("top_k", 60))
        self.timeout_seconds = int(self.config.get("timeout_seconds", 5))
        self.load_error: str | None = None

    def available(self) -> bool:
        return self.enabled and not self.load_error

    def search(self, query: str, top_k: int | None = None) -> list[dict]:
        if not self.available():
            return []

        size = int(top_k or self.top_k)
        body = {
            "size": size,
            "_source": ["row_id", "chunk_id", "cid", "title", "article", "clause", "text"],
            "query": {
                "multi_match": {
                    "query": query,
                    "fields": ["text^2", "title"],
                    "type": "best_fields"
                }
            }
        }
        endpoint = f"{self.url}/{parse.quote(self.index)}/_search"
        req = request.Request(
            endpoint,
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with request.urlopen(req, timeout=self.timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (error.URLError, error.HTTPError, TimeoutError, json.JSONDecodeError) as exc:
            self.load_error = str(exc)
            return []

        results: list[dict] = []
        for hit in payload.get("hits", {}).get("hits", []):
            source = hit.get("_source") or {}
            results.append(
                {
                    "row_id": int(source.get("row_id", -1)),
                    "chunk_id": source.get("chunk_id"),
                    "cid": str(source.get("cid")),
                    "title": source.get("title"),
                    "article": source.get("article"),
                    "clause": source.get("clause"),
                    "text": source.get("text", ""),
                    "es_score": float(hit.get("_score", 0.0)),
                    "sources": ["elasticsearch"],
                }
            )
        return results
