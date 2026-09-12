"""Paired benchmark evaluation: Base vs QLoRA on identical samples.

Ensures both models run on the exact same sample IDs with the same prompts,
decoding, and parsing logic. This is the core validity guarantee for the paper.

Output format per task:
    task_id, sample_id, gold, base_raw, base_parsed, base_correct,
    qlora_raw, qlora_parsed, qlora_correct
"""
from __future__ import annotations

import json
import hashlib
import random
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Callable

from src.evaluation.answer_eval import (
    _token_f1,
    _rouge_l_f1,
    _normalize,
    _has_citation_marker,
)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class EvalSample:
    """A single evaluation sample with fixed ID."""
    sample_id: str
    task_id: str
    question: str
    evidence: str
    gold: str
    choices: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


@dataclass
class PairedResult:
    """Result for one sample, both models."""
    sample_id: str
    task_id: str
    gold: str
    base_raw: str
    base_parsed: str
    base_correct: bool
    base_metric: float
    qlora_raw: str
    qlora_parsed: str
    qlora_correct: bool
    qlora_metric: float


@dataclass
class TaskResult:
    """Aggregated results for one task."""
    task_id: str
    task_type: str
    metric: str
    n: int
    base_score: float
    qlora_score: float
    delta: float
    details: list[PairedResult] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Sample ID generation (deterministic)
# ---------------------------------------------------------------------------

def generate_sample_id(task_id: str, question: str, index: int) -> str:
    """Generate deterministic sample ID from task + question content."""
    content = f"{task_id}::{question}::{index}"
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


def load_paired_samples(
    task_config: dict,
    max_samples: int = 0,
    seed: int = 42,
) -> list[EvalSample]:
    """Load samples for a task, ensuring fixed IDs.

    If the data file doesn't exist, returns empty list (allows incremental
    data creation).
    """
    data_path = Path(task_config["data_path"])
    if not data_path.exists():
        return []

    samples: list[EvalSample] = []
    task_id = task_config.get("task_id", data_path.stem)

    with data_path.open("r", encoding="utf-8") as f:
        for idx, line in enumerate(f):
            if not line.strip():
                continue
            record = json.loads(line)
            question = record.get("question", "")
            evidence = record.get("evidence", "")
            gold = record.get("gold", "")
            choices = record.get("choices", [])

            sample_id = record.get("sample_id") or generate_sample_id(
                task_id, question, idx
            )

            samples.append(
                EvalSample(
                    sample_id=sample_id,
                    task_id=task_id,
                    question=question,
                    evidence=evidence,
                    gold=gold,
                    choices=choices,
                    metadata=record.get("metadata", {}),
                )
            )

    if max_samples > 0 and len(samples) > max_samples:
        rng = random.Random(seed)
        samples = rng.sample(samples, max_samples)

    return samples


def save_eval_ids(samples: list[EvalSample], output_path: Path) -> None:
    """Save fixed eval IDs to JSON for reproducibility."""
    ids = [
        {
            "sample_id": s.sample_id,
            "task_id": s.task_id,
            "question_hash": hashlib.sha256(s.question.encode()).hexdigest()[:12],
        }
        for s in samples
    ]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(ids, indent=2, ensure_ascii=False), encoding="utf-8")


def load_eval_ids(path: Path) -> dict[str, str]:
    """Load fixed eval IDs. Returns {sample_id: task_id}."""
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {item["sample_id"]: item["task_id"] for item in data}


# ---------------------------------------------------------------------------
# Prompt construction (same for both models)
# ---------------------------------------------------------------------------

def build_prompt(sample: EvalSample, task_config: dict) -> str:
    """Build identical prompt for both Base and QLoRA.

    MCQ format:
        Context: {evidence}
        Question: {question}
        A. ...  B. ...  C. ...  D. ...
        Answer with a single letter (A/B/C/D).

    Extraction format:
        Context: {evidence}
        Question: {question}
        Extract the answer from the context.

    Generation format:
        Context: {evidence}
        Question: {question}
        Provide a detailed legal analysis.
    """
    task_type = task_config.get("task_type", "mcq")
    evidence = sample.evidence
    question = sample.question

    base_prompt = f"Van ban phap ly:\n{evidence}\n\nCau hoi:\n{question}"

    if task_type == "mcq":
        choices_text = "\n".join(
            f"  {ch}. {sample.choices[i]}"
            for i, ch in enumerate(task_config.get("choices", ["A", "B", "C", "D"]))
            if i < len(sample.choices)
        )
        return (
            f"{base_prompt}\n\n"
            f"{choices_text}\n\n"
            "Tra loi chi mot chu cai (A/B/C/D)."
        )
    elif task_type == "extraction":
        return (
            f"{base_prompt}\n\n"
            "Trich xuat cau tra loi tu van ban. Tra loi ngan gon."
        )
    elif task_type == "generation":
        return (
            f"{base_prompt}\n\n"
            "Viet phan tich phap ly chi tiet, co can cu ro rang."
        )
    elif task_type == "binary":
        return (
            f"{base_prompt}\n\n"
            "Tra loi 'Co' hoac 'Khong'."
        )
    else:
        return base_prompt


# ---------------------------------------------------------------------------
# Parsing and scoring
# ---------------------------------------------------------------------------

def parse_mcq_response(raw: str, choices: list[str] | None = None) -> str:
    """Parse MCQ response to single letter. Returns first valid letter found."""
    normalized = raw.strip().upper()
    valid = choices or ["A", "B", "C", "D"]
    for letter in valid:
        if normalized == letter:
            return letter
    for letter in valid:
        if letter in normalized:
            return letter
    return normalized[:1] if normalized else ""


def parse_extraction_response(raw: str) -> str:
    """Normalize extraction response."""
    return raw.strip()


def parse_generation_response(raw: str) -> str:
    """Normalize generation response."""
    cleaned = raw.strip()
    import re
    cleaned = re.sub(r"```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE).strip()
    cleaned = re.sub(r"\s*```$", "", cleaned).strip()
    return cleaned


def parse_response(raw: str, task_config: dict) -> str:
    """Route to appropriate parser based on task type."""
    task_type = task_config.get("task_type", "mcq")
    if task_type == "mcq":
        return parse_mcq_response(raw, task_config.get("choices"))
    elif task_type == "extraction":
        return parse_extraction_response(raw)
    elif task_type == "generation":
        return parse_generation_response(raw)
    elif task_type == "binary":
        normalized = raw.strip().lower()
        if normalized.startswith(("co", "yes", "dung")):
            return "Co"
        elif normalized.startswith(("khong", "no", "sai")):
            return "Khong"
        return normalized[:10]
    return raw.strip()


def score_sample(
    parsed: str,
    gold: str,
    task_config: dict,
) -> tuple[bool, float]:
    """Score a parsed response against gold.

    Returns (is_correct, metric_value).
    """
    task_type = task_config.get("task_type", "mcq")
    metric = task_config.get("metric", "accuracy")

    if task_type == "mcq" or task_type == "binary":
        correct = _normalize(parsed) == _normalize(gold)
        return correct, 1.0 if correct else 0.0
    elif metric == "token_f1":
        value = _token_f1(gold, parsed)
        return value > 0.5, value
    elif metric == "rouge_l":
        value = _rouge_l_f1(gold, parsed)
        return value > 0.5, value
    elif metric == "exact_match":
        correct = _normalize(parsed) == _normalize(gold)
        return correct, 1.0 if correct else 0.0
    else:
        value = _token_f1(gold, parsed)
        return value > 0.5, value


# ---------------------------------------------------------------------------
# Core paired evaluation
# ---------------------------------------------------------------------------

def run_paired_evaluation(
    samples: list[EvalSample],
    task_config: dict,
    generate_fn: Callable[[EvalSample, dict], str],
    task_id: str = "",
) -> TaskResult:
    """Run paired evaluation: one model on same samples.

    This is the inner loop. The caller is responsible for providing generate_fn
    that wraps the correct model (Base or QLoRA).

    But for the paired benchmark, we actually run BOTH models on each sample
    in sequence. This function is called once per task with a generate_fn that
    returns both base and qlora predictions.
    """
    task_id = task_id or task_config.get("task_id", "unknown")
    task_type = task_config.get("task_type", "mcq")
    metric_name = task_config.get("metric", "accuracy")

    details: list[PairedResult] = []

    for sample in samples:
        base_raw, qlora_raw = generate_fn(sample, task_config)
        base_parsed = parse_response(base_raw, task_config)
        qlora_parsed = parse_response(qlora_raw, task_config)

        base_correct, base_metric = score_sample(base_parsed, sample.gold, task_config)
        qlora_correct, qlora_metric = score_sample(qlora_parsed, sample.gold, task_config)

        details.append(
            PairedResult(
                sample_id=sample.sample_id,
                task_id=task_id,
                gold=sample.gold,
                base_raw=base_raw,
                base_parsed=base_parsed,
                base_correct=base_correct,
                base_metric=base_metric,
                qlora_raw=qlora_raw,
                qlora_parsed=qlora_parsed,
                qlora_correct=qlora_correct,
                qlora_metric=qlora_metric,
            )
        )

    n = len(details)
    if n == 0:
        return TaskResult(
            task_id=task_id, task_type=task_type, metric=metric_name,
            n=0, base_score=0.0, qlora_score=0.0, delta=0.0, details=[],
        )

    base_score = sum(d.base_metric for d in details) / n
    qlora_score = sum(d.qlora_metric for d in details) / n

    return TaskResult(
        task_id=task_id,
        task_type=task_type,
        metric=metric_name,
        n=n,
        base_score=round(base_score, 4),
        qlora_score=round(qlora_score, 4),
        delta=round(qlora_score - base_score, 4),
        details=details,
    )


def save_paired_results(result: TaskResult, output_dir: Path) -> None:
    """Save paired results to CSV + JSONL."""
    output_dir.mkdir(parents=True, exist_ok=True)

    # CSV summary
    csv_path = output_dir / f"{result.task_id}_paired.csv"
    header = (
        "sample_id,task_id,gold,base_raw,base_parsed,base_correct,base_metric,"
        "qlora_raw,qlora_parsed,qlora_correct,qlora_metric"
    )
    lines = [header]
    for d in result.details:
        line = (
            f'"{d.sample_id}","{d.task_id}","{d.gold}",'
            f'"{d.base_raw}","{d.base_parsed}",{d.base_correct},{d.base_metric},'
            f'"{d.qlora_raw}","{d.qlora_parsed}",{d.qlora_correct},{d.qlora_metric}'
        )
        lines.append(line)
    csv_path.write_text("\n".join(lines), encoding="utf-8")

    # JSONL detailed
    jsonl_path = output_dir / f"{result.task_id}_paired.jsonl"
    with jsonl_path.open("w", encoding="utf-8") as f:
        for d in result.details:
            f.write(json.dumps(asdict(d), ensure_ascii=False) + "\n")

    # Summary JSON
    summary = {
        "task_id": result.task_id,
        "task_type": result.task_type,
        "metric": result.metric,
        "n": result.n,
        "base_score": result.base_score,
        "qlora_score": result.qlora_score,
        "delta": result.delta,
    }
    summary_path = output_dir / f"{result.task_id}_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
