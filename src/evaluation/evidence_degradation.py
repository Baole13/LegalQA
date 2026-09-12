"""Evidence degradation evaluation.

Tests model behavior when evidence is corrupted, incomplete, or absent.
Separates noise robustness from evidence insufficiency awareness.

Conditions:
  C1 Clean         - Original evidence
  C2 Distractor    - Original + irrelevant legal provisions
  C3 Missing Rule  - Key legal rule removed
  C4 Missing Condition - Qualification removed
  C5 Missing Exception - Exception clause removed
  C6 Wrong-Similar - Similar but inapplicable rule substituted
  C7 Empty         - All evidence removed
  C8 Shuffled      - Evidence from a different sample

Metrics per condition:
  - Accuracy / F1 / ROUGE-L (depends on task type)
  - Appropriate Abstention Rate (AAR)
  - Unsupported Conclusion Rate (UCR)
  - Prediction Persistence Rate (PPR)
"""
from __future__ import annotations

import json
import random
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Callable

from src.evaluation.paired_benchmark import (
    EvalSample,
    PairedResult,
    TaskResult,
    parse_response,
    score_sample,
)


# ---------------------------------------------------------------------------
# Condition definitions
# ---------------------------------------------------------------------------

CONDITIONS = {
    "clean": {
        "id": "clean",
        "display_name": "Clean (Original)",
        "description": "Original evidence, no modification",
    },
    "distractor": {
        "id": "distractor",
        "display_name": "Distractor Noise",
        "description": "Original evidence + irrelevant legal provisions as distractors",
    },
    "missing_rule": {
        "id": "missing_rule",
        "display_name": "Missing Rule",
        "description": "Remove the specific legal rule needed to answer",
    },
    "missing_condition": {
        "id": "missing_condition",
        "display_name": "Missing Condition",
        "description": "Remove a condition/qualification from the applicable rule",
    },
    "missing_exception": {
        "id": "missing_exception",
        "display_name": "Missing Exception",
        "description": "Remove exception clauses from the applicable rule",
    },
    "wrong_similar": {
        "id": "wrong_similar",
        "display_name": "Wrong-Similar Rule",
        "description": "Replace with a similar but inapplicable legal provision",
    },
    "empty": {
        "id": "empty",
        "display_name": "Empty Evidence",
        "description": "Remove all legal evidence entirely",
    },
    "shuffled": {
        "id": "shuffled",
        "display_name": "Shuffled Evidence",
        "description": "Use evidence from a different sample",
    },
}


# ---------------------------------------------------------------------------
# Evidence manipulation functions
# ---------------------------------------------------------------------------

def manipulate_evidence(
    sample: EvalSample,
    condition: str,
    all_samples: list[EvalSample] | None = None,
    rng: random.Random | None = None,
) -> str:
    """Apply evidence manipulation for a given condition.

    Returns the modified evidence string.
    """
    evidence = sample.evidence
    if not evidence:
        return ""

    if condition == "clean":
        return evidence

    if condition == "empty":
        return ""

    if condition == "shuffled":
        if all_samples and len(all_samples) > 1:
            rng = rng or random.Random(42)
            candidates = [s for s in all_samples if s.sample_id != sample.sample_id]
            if candidates:
                other = rng.choice(candidates)
                return other.evidence
        return ""

    if condition == "distractor":
        distractor = (
            "\n\n[Distactor] Dieu 1. Luat Xuly vi phanh hanh chinh: "
            "Ngan han xu phat vi phanh hanh chinh la 1 nam ke tu thoi diem "
            "pham vi phanh. Thoi han xu phat khong duoc gia han."
        )
        return evidence + distractor

    if condition in ("missing_rule", "missing_condition", "missing_exception"):
        paragraphs = evidence.split("\n\n")
        if len(paragraphs) <= 1:
            return ""
        # Remove the last paragraph (typically the operative rule)
        return "\n\n".join(paragraphs[:-1])

    if condition == "wrong_similar":
        wrong_evidence = (
            "Dieu 5. Thoi hieu xu phat vi phanh hanh chinh\n"
            "1. Thoi hieu xu phat vi phanh hanh chinh trong linh vuc lao dong, "
            "bao hiem xa hoi la 1 nam ke tu thoi diem pham vi phanh.\n"
            "2. Thoi hieu xu phat vi phanh hanh chinh trong linh vuc moi truong "
            "la 2 nam ke tu thoi diem pham vi phanh."
        )
        return wrong_evidence

    return evidence


# ---------------------------------------------------------------------------
# Degradation result structures
# ---------------------------------------------------------------------------

@dataclass
class DegradationResult:
    """Result for one sample under one condition, one model."""
    sample_id: str
    condition: str
    raw_output: str
    parsed_output: str
    is_correct: bool
    metric_value: float
    prediction_matches_clean: bool = False
    confidence_proxy: float = 0.0


@dataclass
class ConditionAggregate:
    """Aggregated results for one condition across all samples."""
    condition: str
    n: int
    accuracy: float
    avg_metric: float
    appropriate_abstention_rate: float
    unsupported_conclusion_rate: float
    prediction_persistence_rate: float
    details: list[DegradationResult] = field(default_factory=list)


@dataclass
class DegradationTaskReport:
    """Full degradation report for one task, one model."""
    task_id: str
    model_name: str
    clean_accuracy: float
    conditions: dict[str, ConditionAggregate] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Core degradation evaluation
# ---------------------------------------------------------------------------

def run_degradation_single_model(
    samples: list[EvalSample],
    task_config: dict,
    generate_fn: Callable[[EvalSample, str], str],
    model_name: str,
    task_id: str = "",
    seed: int = 42,
) -> DegradationTaskReport:
    """Run evidence degradation for a single model.

    Args:
        samples: Original samples with clean evidence.
        task_config: Task configuration dict.
        generate_fn: Function(sample, evidence_string) -> raw_output.
        model_name: Name of the model (e.g., "base" or "qlora").
        task_id: Task identifier.
        seed: Random seed for shuffling.

    Returns:
        DegradationTaskReport with results for all conditions.
    """
    task_id = task_id or task_config.get("task_id", "unknown")
    rng = random.Random(seed)
    condition_ids = [c["id"] for c in CONDITIONS.values()]

    # First: get clean predictions for persistence comparison
    clean_predictions: dict[str, str] = {}
    clean_results: dict[str, DegradationResult] = {}

    for sample in samples:
        evidence_clean = manipulate_evidence(sample, "clean")
        raw = generate_fn(sample, evidence_clean)
        parsed = parse_response(raw, task_config)
        correct, metric = score_sample(parsed, sample.gold, task_config)
        clean_predictions[sample.sample_id] = parsed
        clean_results[sample.sample_id] = DegradationResult(
            sample_id=sample.sample_id,
            condition="clean",
            raw_output=raw,
            parsed_output=parsed,
            is_correct=correct,
            metric_value=metric,
        )

    clean_accuracy = (
        sum(r.is_correct for r in clean_results.values()) / len(samples)
        if samples else 0.0
    )

    # Then: run each degradation condition
    conditions: dict[str, ConditionAggregate] = {}

    for cond_id in condition_ids:
        cond_details: list[DegradationResult] = []

        for sample in samples:
            evidence = manipulate_evidence(sample, cond_id, all_samples=samples, rng=rng)
            raw = generate_fn(sample, evidence)
            parsed = parse_response(raw, task_config)
            correct, metric = score_sample(parsed, sample.gold, task_config)

            clean_pred = clean_predictions.get(sample.sample_id, "")
            matches_clean = _normalize_str(parsed) == _normalize_str(clean_pred)

            # Abstention detection: model says it can't answer
            is_abstention = _detect_abstention(parsed, task_config)
            # Unsupported conclusion: model gives confident answer without evidence
            is_unsupported = not is_abstention and not correct and cond_id != "clean"

            conf_proxy = _confidence_proxy(parsed, task_config)

            cond_details.append(
                DegradationResult(
                    sample_id=sample.sample_id,
                    condition=cond_id,
                    raw_output=raw,
                    parsed_output=parsed,
                    is_correct=correct,
                    metric_value=metric,
                    prediction_matches_clean=matches_clean,
                    confidence_proxy=conf_proxy,
                )
            )

        n = len(cond_details)
        accuracy = sum(r.is_correct for r in cond_details) / n if n else 0.0
        avg_metric = sum(r.metric_value for r in cond_details) / n if n else 0.0

        # AAR: fraction of samples where model appropriately abstains
        # when evidence is degraded (not clean)
        if cond_id == "clean":
            aar = 0.0
        else:
            abstentions = sum(1 for r in cond_details if _detect_abstention(r.parsed_output, task_config))
            aar = abstentions / n if n else 0.0

        # UCR: fraction of samples where model gives wrong confident answer
        if cond_id == "clean":
            ucr = 0.0
        else:
            unsupported = sum(
                1 for r in cond_details
                if not _detect_abstention(r.parsed_output, task_config) and not r.is_correct
            )
            ucr = unsupported / n if n else 0.0

        # PPR: fraction of predictions that match clean prediction
        if cond_id == "clean":
            ppr = 1.0
        else:
            persistence = sum(1 for r in cond_details if r.prediction_matches_clean)
            ppr = persistence / n if n else 0.0

        conditions[cond_id] = ConditionAggregate(
            condition=cond_id,
            n=n,
            accuracy=round(accuracy, 4),
            avg_metric=round(avg_metric, 4),
            appropriate_abstention_rate=round(aar, 4),
            unsupported_conclusion_rate=round(ucr, 4),
            prediction_persistence_rate=round(ppr, 4),
            details=cond_details,
        )

    return DegradationTaskReport(
        task_id=task_id,
        model_name=model_name,
        clean_accuracy=round(clean_accuracy, 4),
        conditions=conditions,
    )


def _normalize_str(s: str) -> str:
    return s.strip().lower()


def _detect_abstention(parsed: str, task_config: dict) -> bool:
    """Detect if model is abstaining (saying it can't answer)."""
    normalized = parsed.lower().strip()
    abstention_markers = [
        "khong du can cu",
        "khong the tra loi",
        "khong xac dinh",
        "thieu thong tin",
        "can bo sung",
        "khong co du thong tin",
        "khong biet",
        "khong ro",
        "khong chac chan",
    ]
    return any(marker in normalized for marker in abstention_markers)


def _confidence_proxy(parsed: str, task_config: dict) -> float:
    """Estimate confidence from output characteristics."""
    task_type = task_config.get("task_type", "mcq")
    if task_type == "mcq":
        # Single letter = high confidence, long text = low confidence
        stripped = parsed.strip()
        if len(stripped) <= 2:
            return 1.0
        elif len(stripped) <= 10:
            return 0.7
        return 0.3
    elif task_type == "binary":
        if parsed.strip().lower() in ("co", "khong"):
            return 1.0
        return 0.5
    else:
        if len(parsed) < 20:
            return 0.3
        return 0.7


# ---------------------------------------------------------------------------
# Noise robustness metrics
# ---------------------------------------------------------------------------

def compute_noise_robustness_drop(
    clean_accuracy: float,
    distractor_accuracy: float,
) -> float:
    """Noise Robustness Drop = Clean Accuracy - Distractor Accuracy.

    Lower is better (less affected by distractors).
    """
    return round(clean_accuracy - distractor_accuracy, 4)


# ---------------------------------------------------------------------------
# Saving results
# ---------------------------------------------------------------------------

def save_degradation_report(
    report: DegradationTaskReport,
    output_dir: Path,
) -> None:
    """Save degradation report to files."""
    output_dir.mkdir(parents=True, exist_ok=True)

    # Summary JSON
    summary = {
        "task_id": report.task_id,
        "model_name": report.model_name,
        "clean_accuracy": report.clean_accuracy,
        "conditions": {},
    }
    for cond_id, cond in report.conditions.items():
        summary["conditions"][cond_id] = {
            "n": cond.n,
            "accuracy": cond.accuracy,
            "avg_metric": cond.avg_metric,
            "appropriate_abstention_rate": cond.appropriate_abstention_rate,
            "unsupported_conclusion_rate": cond.unsupported_conclusion_rate,
            "prediction_persistence_rate": cond.prediction_persistence_rate,
        }

    summary_path = output_dir / f"{report.task_id}_{report.model_name}_degradation.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    # Detailed JSONL
    jsonl_path = output_dir / f"{report.task_id}_{report.model_name}_degradation.jsonl"
    with jsonl_path.open("w", encoding="utf-8") as f:
        for cond_id, cond in report.conditions.items():
            for detail in cond.details:
                record = asdict(detail)
                record["model_name"] = report.model_name
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
