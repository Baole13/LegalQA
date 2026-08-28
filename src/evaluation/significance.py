from __future__ import annotations

import json
import random
from pathlib import Path

CACHE_DIR = Path("reports/.paper_experiment_cache")


def load_details(cache_dir: Path, variant: str, limit: int, top_k: int) -> list[dict]:
    path = cache_dir / f"retrieval_v2_{variant}_limit{limit}_top{top_k}.jsonl"
    if not path.exists():
        raise FileNotFoundError(f"missing cache: {path}")
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def per_query_scores(details: list[dict], metric: str, k: int) -> dict[int, float]:
    scores: dict[int, float] = {}
    for item in details:
        gold = {str(cid) for cid in item.get("gold_cids", [])}
        ranked = [str(hit.get("cid", "")) for hit in (item.get("retrieved") or [])]
        if metric == "recall":
            value = float(any(cid in gold for cid in ranked[:k]))
        elif metric == "mrr":
            value = 0.0
            for rank, cid in enumerate(ranked, start=1):
                if cid in gold:
                    value = 1.0 / rank
                    break
        else:
            raise ValueError(f"unknown metric {metric}")
        scores[int(item["sample_index"])] = value
    return scores


def bootstrap_ci(values: list[float], iterations: int, rng: random.Random) -> dict:
    n = len(values)
    means = []
    for _ in range(iterations):
        means.append(sum(values[rng.randrange(n)] for _ in range(n)) / n)
    means.sort()
    return {
        "mean": round(sum(values) / n, 4),
        "ci_low": round(means[int(0.025 * iterations)], 4),
        "ci_high": round(means[int(0.975 * iterations)], 4),
    }


def paired_bootstrap_p(
    baseline: list[float],
    treatment: list[float],
    iterations: int,
    rng: random.Random,
) -> float:
    """
    Two-sided paired bootstrap test on the mean difference (Berg-Kirkpatrick et al., 2012).
    Counts resamples where the shifted difference exceeds twice the observed one.
    """
    n = len(baseline)
    deltas = [t - b for b, t in zip(baseline, treatment)]
    observed = sum(deltas) / n
    count = 0
    for _ in range(iterations):
        resampled = sum(deltas[rng.randrange(n)] for _ in range(n)) / n
        if abs(resampled - observed) >= abs(observed):
            count += 1
    return round(count / iterations, 4)


def compare(
    cache_dir: Path,
    baseline_variant: str,
    treatment_variant: str,
    limit: int,
    top_k: int,
    iterations: int,
    seed: int,
) -> dict:
    baseline_details = load_details(cache_dir, baseline_variant, limit, top_k)
    treatment_details = load_details(cache_dir, treatment_variant, limit, top_k)
    comparisons = []
    for metric, k in (("recall", 1), ("recall", 5), ("recall", 10), ("mrr", top_k)):
        base_scores = per_query_scores(baseline_details, metric, k)
        treat_scores = per_query_scores(treatment_details, metric, k)
        shared = sorted(set(base_scores) & set(treat_scores))
        base_values = [base_scores[i] for i in shared]
        treat_values = [treat_scores[i] for i in shared]
        rng = random.Random(seed)
        comparisons.append(
            {
                "metric": f"{metric}@{k}" if metric == "recall" else metric,
                "paired_samples": len(shared),
                "baseline": bootstrap_ci(base_values, iterations, random.Random(seed)),
                "treatment": bootstrap_ci(treat_values, iterations, random.Random(seed + 1)),
                "delta": round(
                    sum(treat_values) / len(shared) - sum(base_values) / len(shared), 4
                ),
                "p_value": paired_bootstrap_p(base_values, treat_values, iterations, rng),
            }
        )
    return {
        "baseline_variant": baseline_variant,
        "treatment_variant": treatment_variant,
        "limit": limit,
        "top_k": top_k,
        "bootstrap_iterations": iterations,
        "seed": seed,
        "comparisons": comparisons,
    }
