from __future__ import annotations

import time
from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from src.api.schemas import AskRequest, RetrievalDebugRequest
from src.evaluation.retrieval_eval import evaluate_retrieval
from src.indexing.artifacts import build_full_artifacts
from src.qa.pipeline import LegalQAPipeline
from src.utils.exceptions import LegalQAException, ValidationError
from src.utils.logger import get_logger

logger = get_logger(__name__)

app = FastAPI(title="Vietnamese Legal QA", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(ValidationError)
async def validation_error_handler(request, exc: ValidationError):
    """Handle validation errors with proper HTTP status code."""
    logger.warning(f"Validation error: {exc.message}")
    return HTTPException(status_code=400, detail=exc.message)


@app.exception_handler(LegalQAException)
async def legal_qa_error_handler(request, exc: LegalQAException):
    """Handle LegalQA errors with proper HTTP status code."""
    logger.error(f"LegalQA error [{exc.error_code}]: {exc.message}")
    return HTTPException(status_code=500, detail=f"{exc.error_code}: {exc.message}")


@app.exception_handler(Exception)
async def general_error_handler(request, exc: Exception):
    """Handle unexpected errors."""
    logger.exception(f"Unexpected error: {exc}")
    return HTTPException(status_code=500, detail="Internal server error")


frontend_dir = Path("frontend")
if frontend_dir.exists():
    app.mount("/static", StaticFiles(directory=frontend_dir), name="static")


@lru_cache(maxsize=1)
def get_pipeline() -> LegalQAPipeline:
    return LegalQAPipeline.build()


@app.on_event("startup")
def warm_pipeline() -> None:
    """Warm up the pipeline on startup."""
    try:
        logger.info("Warming up pipeline...")
        pipeline = get_pipeline()
        logger.info(
            f"Pipeline ready: {pipeline.artifacts.store.manifest['corpus_chunks']} chunks, "
            f"{pipeline.artifacts.store.manifest['qa_memory_records']} QA records"
        )
    except Exception as e:
        logger.error(f"Failed to warm up pipeline: {e}")
        raise



@app.get("/")
def root() -> FileResponse:
    return FileResponse(frontend_dir / "index.html")


@app.get("/health")
def health() -> dict:
    pipeline = get_pipeline()
    return {
        "status": "ok",
        "chunks": pipeline.artifacts.store.manifest["corpus_chunks"],
        "qa_memory_records": pipeline.artifacts.store.manifest["qa_memory_records"],
        "artifact_version": pipeline.artifacts.store.manifest["version"],
        "retriever_mode": "embedding-boosted" if pipeline.artifacts.retriever.embedding_retriever.available() else "sparse-hybrid",
        "retriever_model_path": pipeline.serving_config.retriever_model_path,
        "reranker_mode": "cross-encoder" if pipeline.model_reranker.available() else "heuristic",
        "reranker_model_path": pipeline.serving_config.reranker_model_path,
        "llm_loaded": pipeline.reasoner.loaded,
        "llm_enabled": pipeline.serving_config.use_llm_reasoning,
        "llm_config_path": pipeline.serving_config.llm_config_path,
        "llm_error": pipeline.reasoner.load_error,
    }


@app.post("/ask")
def ask(payload: AskRequest) -> dict:
    """Process a legal question and return an answer with supporting context."""
    try:
        start_time = time.time()
        logger.info(f"Processing question: '{payload.question[:50]}...' (top_k={payload.top_k})")
        
        result = get_pipeline().ask(payload.question, top_k=payload.top_k)
        
        elapsed = time.time() - start_time
        logger.info(
            f"Question processed successfully in {elapsed:.2f}s: "
            f"{len(result.get('retrieval', []))} results"
        )
        return result
    except Exception as e:
        logger.error(f"Failed to process question: {e}")
        raise



@app.post("/retrieval_debug")
def retrieval_debug(payload: RetrievalDebugRequest) -> dict:
    """Debug endpoint for retrieval results without answer generation."""
    try:
        logger.debug(f"Retrieval debug for: '{payload.question[:50]}...' (top_k={payload.top_k})")
        result = get_pipeline().retrieval_debug(payload.question, top_k=payload.top_k)
        return result
    except Exception as e:
        logger.error(f"Retrieval debug failed: {e}")
        raise



@app.post("/reindex")
def reindex(force: bool = True) -> dict:
    """Rebuild all artifacts and indexes."""
    try:
        logger.info(f"Starting reindex (force={force})...")
        start_time = time.time()
        
        build_full_artifacts(force=force)
        get_pipeline.cache_clear()
        pipeline = get_pipeline()
        
        elapsed = time.time() - start_time
        logger.info(
            f"Reindex completed in {elapsed:.2f}s: "
            f"{pipeline.artifacts.store.manifest['corpus_chunks']} chunks, "
            f"{pipeline.artifacts.store.manifest['qa_memory_records']} QA records"
        )
        
        return {
            "status": "reindexed",
            "chunks": pipeline.artifacts.store.manifest["corpus_chunks"],
            "qa_memory_records": pipeline.artifacts.store.manifest["qa_memory_records"],
            "elapsed_seconds": elapsed,
        }
    except Exception as e:
        logger.error(f"Reindex failed: {e}")
        raise



@app.get("/eval")
def run_eval(limit: int = 100) -> dict:
    """Run retrieval evaluation on test set."""
    try:
        logger.info(f"Starting evaluation with limit={limit}")
        start_time = time.time()
        
        result = evaluate_retrieval(get_pipeline(), limit=limit)
        
        elapsed = time.time() - start_time
        logger.info(f"Evaluation completed in {elapsed:.2f}s")
        
        return result
    except Exception as e:
        logger.error(f"Evaluation failed: {e}")
        raise

