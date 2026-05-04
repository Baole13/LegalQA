from __future__ import annotations

from dataclasses import dataclass

from src.qa.llm_reasoner import QwenReasoner
from src.indexing.artifacts import IndexedArtifactStore, artifacts_exist, build_full_artifacts
from src.qa.context_builder import build_context
from src.qa.generator import ExtractiveAnswerGenerator
from src.reranker.cross_encoder_reranker import HeuristicReranker
from src.reranker.model_reranker import OptionalCrossEncoderReranker
from src.retrieval.hybrid_retriever import HybridRetriever
from src.serving.config import ServingConfig, load_serving_config
from src.utils.logger import get_logger

logger = get_logger(__name__)



@dataclass
class PipelineArtifacts:
    store: IndexedArtifactStore
    retriever: HybridRetriever


class LegalQAPipeline:
    def __init__(self, artifacts: PipelineArtifacts, serving_config: ServingConfig):
        self.artifacts = artifacts
        self.serving_config = serving_config
        self.heuristic_reranker = HeuristicReranker()
        self.model_reranker = OptionalCrossEncoderReranker(model_path=serving_config.reranker_model_path)
        self.reasoner = QwenReasoner(config_path=serving_config.llm_config_path)
        if not serving_config.use_llm_reasoning:
            self.reasoner.enabled = False
        self.generator = ExtractiveAnswerGenerator(reasoner=self.reasoner)

    @classmethod
    def build(cls, force_reindex: bool = False) -> "LegalQAPipeline":
        if force_reindex or not artifacts_exist():
            build_full_artifacts(force=force_reindex)
        store = IndexedArtifactStore()
        serving_config = load_serving_config()
        artifacts = PipelineArtifacts(
            store=store,
            retriever=HybridRetriever(store, retriever_model_path=serving_config.retriever_model_path),
        )
        return cls(artifacts, serving_config)

    def ask(self, question: str, top_k: int = 5) -> dict:
        """Process a legal question through the full pipeline."""
        try:
            logger.debug(f"Starting pipeline for: '{question[:60]}...'")
            
            # Stage 1: Find similar questions
            similar_questions = self.artifacts.retriever.similar_questions(question, top_k=5)
            logger.debug(f"Found {len(similar_questions)} similar questions")
            
            # Stage 2: Retrieve candidates
            candidates = self.artifacts.retriever.search(question, top_k=max(top_k * 2, 10))
            logger.debug(f"Retrieved {len(candidates)} candidates from hybrid search")
            
            # Stage 3: Add QA memory candidates
            qa_memory = self._qa_memory_candidates(similar_questions)
            candidates.extend(qa_memory)
            logger.debug(f"Added {len(qa_memory)} QA memory candidates (total: {len(candidates)})")
            
            # Stage 4: Heuristic reranking
            heuristic = self.heuristic_reranker.rerank(question, candidates, top_k=max(top_k * 2, 10))
            logger.debug(f"After heuristic rerank: {len(heuristic)} candidates")
            
            # Stage 5: Model reranking
            reranked = self.model_reranker.rerank(question, heuristic, top_k=top_k)
            logger.debug(f"After model rerank: {len(reranked)} final candidates")
            
            # Stage 6: Generate answer
            generated = self.generator.generate(question, reranked, similar_questions=similar_questions)
            logger.debug(f"Answer generated (mode: {generated.get('generator_mode', 'extractive')})")
            
            # Assemble result
            generated["question"] = question
            generated["context"] = build_context(reranked)
            generated["retrieval"] = reranked
            generated["system"] = {
                "chunks": self.artifacts.store.manifest["corpus_chunks"],
                "qa_memory_records": self.artifacts.store.manifest["qa_memory_records"],
                "artifact_version": self.artifacts.store.manifest["version"],
                "retriever_model_path": self.serving_config.retriever_model_path,
                "reranker_mode": "cross-encoder" if self.model_reranker.available() else "heuristic",
                "reranker_model_path": self.serving_config.reranker_model_path,
                "generator_mode": generated.get("generator_mode", "extractive"),
                "llm_loaded": self.reasoner.loaded,
                "llm_config_path": self.serving_config.llm_config_path,
            }
            
            logger.info(f"Pipeline completed: retrieved {len(reranked)} results for answer")
            return generated
            
        except Exception as e:
            logger.exception(f"Pipeline failed: {e}")
            raise

    def retrieval_debug(self, question: str, top_k: int = 10) -> dict:
        return {
            "question": question,
            "results": self.artifacts.retriever.search(question, top_k=top_k),
            "similar_questions": self.artifacts.retriever.similar_questions(question, top_k=5),
        }

    def _qa_memory_candidates(self, similar_questions: list[dict]) -> list[dict]:
        candidates: list[dict] = []
        for item in similar_questions[:3]:
            qa_score = float(item.get("qa_score", 0.0))
            if qa_score < 0.55:
                continue
            contexts = item.get("contexts") or []
            cids = item.get("cids") or ["qa-memory"]
            for index, context in enumerate(contexts[:2]):
                candidates.append(
                    {
                        "row_id": -1,
                        "chunk_id": f"qa-memory:{item['qid']}:{index}",
                        "cid": cids[min(index, len(cids) - 1)],
                        "title": "QA Memory",
                        "article": None,
                        "clause": None,
                        "text": context,
                        "bm25_score": 0.0,
                        "dense_score": 0.0,
                        "qa_boost": qa_score,
                        "hybrid_score": qa_score * 2.0,
                    }
                )
        return candidates
