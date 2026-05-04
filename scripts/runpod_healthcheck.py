from __future__ import annotations

from src.qa.pipeline import LegalQAPipeline


def main() -> None:
    pipeline = LegalQAPipeline.build()
    health = {
        "chunks": pipeline.artifacts.store.manifest["corpus_chunks"],
        "qa_memory_records": pipeline.artifacts.store.manifest["qa_memory_records"],
        "retriever_mode": "embedding-boosted" if pipeline.artifacts.retriever.embedding_retriever.available() else "sparse-hybrid",
        "retriever_model_path": pipeline.serving_config.retriever_model_path,
        "reranker_mode": "cross-encoder" if pipeline.model_reranker.available() else "heuristic",
        "reranker_model_path": pipeline.serving_config.reranker_model_path,
        "llm_enabled": pipeline.serving_config.use_llm_reasoning,
        "llm_loaded": pipeline.reasoner.loaded,
        "llm_config_path": pipeline.serving_config.llm_config_path,
        "llm_error": pipeline.reasoner.load_error,
    }
    print(health)


if __name__ == "__main__":
    main()
