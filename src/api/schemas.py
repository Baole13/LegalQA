from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    question: str = Field(..., min_length=3)
    top_k: int = Field(default=5, ge=1, le=10)
    force_llm_reasoning: bool = False
    debug_llm: bool = False


class RetrievalDebugRequest(BaseModel):
    question: str = Field(..., min_length=3)
    top_k: int = Field(default=10, ge=1, le=20)




class CitationItem(BaseModel):
    chunk_id: str | None = None
    cid: str | None = None
    title: str | None = None
    article: str | None = None
    clause: str | None = None
    label: str | None = None


class EvidenceItem(BaseModel):
    chunk_id: str | None = None
    cid: str | None = None
    text: str = ""
    score: float | None = None
    keyword_coverage: float = 0.0
    phrase_coverage: float = 0.0
    qa_boost: float = 0.0


class AskResponse(BaseModel):
    question: str
    answer: str
    legal_basis: list[str] = []
    reasoning: str = ""
    missing_info: list[str] = []
    confidence: str = "low"
    citations: list[CitationItem] = []
    quotes: list[dict[str, Any]] = []
    evidence: list[EvidenceItem] = []
    retrieval: list[dict[str, Any]] = []
    similar_questions: list[dict[str, Any]] = []
    context: str = ""
    system: dict[str, Any] = {}
    generator_mode: str = "extractive"
    reason: str = "ok"
    llm_debug: dict[str, Any] = {}
