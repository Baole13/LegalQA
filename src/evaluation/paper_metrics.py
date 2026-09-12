"""Paper-grade statistical metrics for paired evaluation.

Includes:
  - McNemar test for classification tasks
  - Paired bootstrap confidence intervals
  - Appropriate Abstention Rate (AAR)
  - Unsupported Conclusion Rate (UCR)
  - Prediction Persistence Rate (PPR)
  - Noise Robustness Drop
  - Bootstrap CI for all metrics
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Sequence


# ---------------------------------------------------------------------------
# McNemar test (for MCQ / binary classification)
# ---------------------------------------------------------------------------

@dataclass
class McNemarResult:
    """Result of McNemar's test for paired binary outcomes."""
    n_disagree: int
    n_base_only_correct: int
    n_qlora_only_correct: int
    chi2: float
    p_value: float
    significant_005: bool
    significant_001: bool


def mcnemar_test(
    base_correct: Sequence[bool],
    qlora_correct: Sequence[bool],
) -> McNemarResult:
    """McNemar's test for paired nominal data.

    Tests whether the two models have significantly different error rates.

    Contingency table:
                    QLoRA Correct  QLoRA Wrong
    Base Correct         a             b
    Base Wrong           c             d

    McNemar chi2 = (b - c)^2 / (b + c)

    With continuity correction: chi2 = (|b - c| - 1)^2 / (b + c)
    """
    assert len(base_correct) == len(qlora_correct), "Paired sequences must match"

    b = sum(1 for bc, qc in zip(base_correct, qlora_correct) if bc and not qc)
    c = sum(1 for bc, qc in zip(base_correct, qlora_correct) if not bc and qc)
    n_disagree = b + c

    if n_disagree == 0:
        return McNemarResult(
            n_disagree=0,
            n_base_only_correct=0,
            n_qlora_only_correct=0,
            chi2=0.0,
            p_value=1.0,
            significant_005=False,
            significant_001=False,
        )

    # With continuity correction
    chi2 = (abs(b - c) - 1) ** 2 / n_disagree

    # p-value from chi2 distribution with 1 df
    p_value = _chi2_p_value_1df(chi2)

    return McNemarResult(
        n_disagree=n_disagree,
        n_base_only_correct=b,
        n_qlora_only_correct=c,
        chi2=round(chi2, 4),
        p_value=round(p_value, 4),
        significant_005=p_value < 0.05,
        significant_001=p_value < 0.01,
    )


def _chi2_p_value_1df(x: float) -> float:
    """Approximate p-value for chi2 with 1 degree of freedom.

    Uses the complementary error function approximation.
    """
    if x <= 0:
        return 1.0
    z = math.sqrt(x)
    # p = 2 * (1 - Phi(z)) where Phi is standard normal CDF
    # Using approximation: 1 - Phi(z) ≈ 0.5 * erfc(z / sqrt(2))
    return math.erfc(z / math.sqrt(2))


# ---------------------------------------------------------------------------
# Paired bootstrap
# ---------------------------------------------------------------------------

@dataclass
class BootstrapCI:
    """Bootstrap confidence interval result."""
    mean: float
    ci_low: float
    ci_high: float
    iterations: int


def paired_bootstrap_ci(
    base_values: Sequence[float],
    qlora_values: Sequence[float],
    iterations: int = 1000,
    seed: int = 42,
    ci_level: float = 0.95,
) -> dict:
    """Paired bootstrap CI for the mean difference.

    Returns dict with baseline CI, treatment CI, delta CI, and p-value.
    """
    assert len(base_values) == len(qlora_values)
    n = len(base_values)
    rng = random.Random(seed)

    deltas = [q - b for b, q in zip(base_values, qlora_values)]
    observed_delta = sum(deltas) / n

    # Bootstrap resampling
    boot_deltas: list[float] = []
    boot_base_means: list[float] = []
    boot_qlora_means: list[float] = []

    for _ in range(iterations):
        indices = [rng.randrange(n) for _ in range(n)]
        boot_deltas.append(sum(deltas[i] for i in indices) / n)
        boot_base_means.append(sum(base_values[i] for i in indices) / n)
        boot_qlora_means.append(sum(qlora_values[i] for i in indices) / n)

    boot_deltas.sort()
    boot_base_means.sort()
    boot_qlora_means.sort()

    alpha = 1 - ci_level
    lo_idx = int(alpha / 2 * iterations)
    hi_idx = int((1 - alpha / 2) * iterations) - 1

    # Two-sided p-value: proportion of bootstrap deltas with opposite sign
    p_value = sum(1 for d in boot_deltas if d * observed_delta <= 0) / iterations

    return {
        "baseline": {
            "mean": round(sum(base_values) / n, 4),
            "ci_low": round(boot_base_means[lo_idx], 4),
            "ci_high": round(boot_base_means[hi_idx], 4),
        },
        "qlora": {
            "mean": round(sum(qlora_values) / n, 4),
            "ci_low": round(boot_qlora_means[lo_idx], 4),
            "ci_high": round(boot_qlora_means[hi_idx], 4),
        },
        "delta": {
            "mean": round(observed_delta, 4),
            "ci_low": round(boot_deltas[lo_idx], 4),
            "ci_high": round(boot_deltas[hi_idx], 4),
        },
        "p_value": round(p_value, 4),
        "iterations": iterations,
        "n": n,
    }


def bootstrap_ci_single(
    values: Sequence[float],
    iterations: int = 1000,
    seed: int = 42,
    ci_level: float = 0.95,
) -> BootstrapCI:
    """Bootstrap CI for a single metric."""
    n = len(values)
    rng = random.Random(seed)
    means: list[float] = []

    for _ in range(iterations):
        sample = [values[rng.randrange(n)] for _ in range(n)]
        means.append(sum(sample) / n)

    means.sort()
    alpha = 1 - ci_level
    lo_idx = int(alpha / 2 * iterations)
    hi_idx = int((1 - alpha / 2) * iterations) - 1

    return BootstrapCI(
        mean=round(sum(values) / n, 4),
        ci_low=round(means[lo_idx], 4),
        ci_high=round(means[hi_idx], 4),
        iterations=iterations,
    )


# ---------------------------------------------------------------------------
# Degradation-specific metrics
# ---------------------------------------------------------------------------

def appropriate_abstention_rate(
    predictions: Sequence[str],
    conditions: Sequence[str],
    gold: Sequence[str],
) -> float:
    """AAR: fraction of degraded samples where model appropriately abstains.

    Only counts samples where condition != "clean".
    """
    count = 0
    total = 0
    for pred, cond, g in zip(predictions, conditions, gold):
        if cond == "clean":
            continue
        total += 1
        if _is_abstention(pred):
            count += 1
    return round(count / total, 4) if total > 0 else 0.0


def unsupported_conclusion_rate(
    predictions: Sequence[str],
    conditions: Sequence[str],
    correct: Sequence[bool],
) -> float:
    """UCR: fraction of degraded samples where model gives wrong confident answer.

    A prediction is "unsupported" if it's not an abstention and is incorrect.
    """
    count = 0
    total = 0
    for pred, cond, cor in zip(predictions, conditions, correct):
        if cond == "clean":
            continue
        total += 1
        if not _is_abstention(pred) and not cor:
            count += 1
    return round(count / total, 4) if total > 0 else 0.0


def prediction_persistence_rate(
    clean_predictions: Sequence[str],
    degraded_predictions: Sequence[str],
    conditions: Sequence[str],
) -> float:
    """PPR: fraction of degraded predictions that match the clean prediction.

    High PPR with degraded evidence = model is NOT using evidence.
    """
    count = 0
    total = 0
    for clean, degraded, cond in zip(clean_predictions, degraded_predictions, conditions):
        if cond == "clean":
            continue
        total += 1
        if _normalize_str(clean) == _normalize_str(degraded):
            count += 1
    return round(count / total, 4) if total > 0 else 0.0


def noise_robustness_drop(clean_accuracy: float, distractor_accuracy: float) -> float:
    """Clean Accuracy - Distractor Accuracy. Lower = more robust."""
    return round(clean_accuracy - distractor_accuracy, 4)


def _is_abstention(parsed: str) -> bool:
    normalized = parsed.lower().strip()
    markers = [
        "khong du can cu", "khong the tra loi", "khong xac dinh",
        "thieu thong tin", "can bo sung", "khong co du thong tin",
        "khong biet", "khong ro", "khong chac chan",
    ]
    return any(m in normalized for m in markers)


def _normalize_str(s: str) -> str:
    return s.strip().lower()


# ---------------------------------------------------------------------------
# Comprehensive statistical report
# ---------------------------------------------------------------------------

def compute_task_statistics(
    base_correct: Sequence[bool],
    qlora_correct: Sequence[bool],
    base_metrics: Sequence[float],
    qlora_metrics: Sequence[float],
    task_type: str,
    metric_name: str,
    task_id: str,
    n: int,
    iterations: int = 1000,
    seed: int = 42,
) -> dict:
    """Compute all statistical tests for a task.

    Returns a comprehensive dict suitable for paper tables.
    """
    result = {
        "task_id": task_id,
        "task_type": task_type,
        "metric": metric_name,
        "n": n,
    }

    # Basic scores
    base_score = sum(base_metrics) / n if n else 0.0
    qlora_score = sum(qlora_metrics) / n if n else 0.0
    result["base_score"] = round(base_score, 4)
    result["qlora_score"] = round(qlora_score, 4)
    result["delta"] = round(qlora_score - base_score, 4)

    # Bootstrap CI for the metric
    bootstrap = paired_bootstrap_ci(
        base_metrics, qlora_metrics,
        iterations=iterations, seed=seed,
    )
    result["bootstrap"] = bootstrap

    # McNemar test for classification tasks
    if task_type in ("mcq", "binary"):
        mcnemar = mcnemar_test(base_correct, qlora_correct)
        result["mcnemar"] = {
            "n_disagree": mcnemar.n_disagree,
            "n_base_only_correct": mcnemar.n_base_only_correct,
            "n_qlora_only_correct": mcnemar.n_qlora_only_correct,
            "chi2": mcnemar.chi2,
            "p_value": mcnemar.p_value,
            "significant_005": mcnemar.significant_005,
            "significant_001": mcnemar.significant_001,
        }

    # Accuracy bootstrap CI for classification
    if task_type in ("mcq", "binary"):
        base_acc = [1.0 if c else 0.0 for c in base_correct]
        qlora_acc = [1.0 if c else 0.0 for c in qlora_correct]
        result["accuracy_ci"] = paired_bootstrap_ci(
            base_acc, qlora_acc,
            iterations=iterations, seed=seed,
        )

    return result
