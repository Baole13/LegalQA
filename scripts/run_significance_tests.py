from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.evaluation.significance import CACHE_DIR, compare
from src.utils.io import save_json

DEFAULT_PAIRS = [
    ("bm25_okapi_only", "full_with_cross_encoder_reranker"),
    ("dense_only", "full_with_cross_encoder_reranker"),
    ("hybrid_no_qa_memory", "hybrid_with_qa_memory"),
    ("full", "full_with_cross_encoder_reranker"),
    ("full_with_cross_encoder_reranker", "full_with_cross_encoder_reranker_k100"),
    ("full_with_cross_encoder_reranker", "full_with_cross_encoder_reranker_hardneg"),
    ("full_with_cross_encoder_reranker", "full_with_cross_encoder_reranker_hardneg_v2"),
]


def render_markdown(results: list[dict]) -> str:
    lines = [
        "# Retrieval Significance Tests",
        "",
        "Paired bootstrap over per-query scores from the cached retrieval details "
        "(Berg-Kirkpatrick et al., 2012). CIs are percentile bootstrap on the mean.",
        "",
        "| baseline | treatment | metric | baseline mean [95% CI] | treatment mean [95% CI] | delta | p |",
        "|---|---|---|---|---|---:|---:|",
    ]
    for result in results:
        for row in result["comparisons"]:
            base = row["baseline"]
            treat = row["treatment"]
            lines.append(
                "| `{b}` | `{t}` | {m} | {bm} [{bl}, {bh}] | {tm} [{tl}, {th}] | {d:+.4f} | {p} |".format(
                    b=result["baseline_variant"],
                    t=result["treatment_variant"],
                    m=row["metric"],
                    bm=base["mean"],
                    bl=base["ci_low"],
                    bh=base["ci_high"],
                    tm=treat["mean"],
                    tl=treat["ci_low"],
                    th=treat["ci_high"],
                    d=row["delta"],
                    p=row["p_value"],
                )
            )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Paired bootstrap significance tests for retrieval ablations")
    parser.add_argument("--cache-dir", default=str(CACHE_DIR))
    parser.add_argument("--limit", type=int, default=300)
    parser.add_argument("--top-k", type=int, default=20)
    parser.add_argument("--iterations", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--report-dir", default="reports")
    args = parser.parse_args()

    cache_dir = Path(args.cache_dir)
    results = []
    skipped = []
    for baseline, treatment in DEFAULT_PAIRS:
        try:
            results.append(
                compare(
                    cache_dir,
                    baseline,
                    treatment,
                    args.limit,
                    args.top_k,
                    args.iterations,
                    args.seed,
                )
            )
        except FileNotFoundError as error:
            skipped.append(str(error))

    report_dir = Path(args.report_dir)
    payload = {"results": results, "skipped": skipped}
    save_json(report_dir / "retrieval_significance.json", payload)
    (report_dir / "retrieval_significance.md").write_text(render_markdown(results), encoding="utf-8")
    print(json.dumps({"pairs_tested": len(results), "skipped": skipped}, indent=2))


if __name__ == "__main__":
    main()
