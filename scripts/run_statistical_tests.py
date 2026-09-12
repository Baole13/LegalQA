"""Run comprehensive statistical tests on paired benchmark results.

Reads paired results from run_paired_benchmark.py and computes:
  - McNemar test (for MCQ/binary tasks)
  - Paired bootstrap 95% CI
  - Delta + CI + p-value per task
  - Summary suitable for paper Table 2

Usage:
    python scripts/run_statistical_tests.py --results-dir results/paired_benchmark
    python scripts/run_statistical_tests.py --results-dir results/paired_benchmark --iterations 2000
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import scripts._bootstrap as _bootstrap  # noqa: F401

from src.evaluation.paper_metrics import (
    compute_task_statistics,
    mcnemar_test,
    paired_bootstrap_ci,
    bootstrap_ci_single,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run statistical tests on paired results.")
    parser.add_argument(
        "--results-dir",
        default="results/paired_benchmark",
        help="Directory with paired benchmark results.",
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=1000,
        help="Bootstrap iterations.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed.",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output JSON path (default: results-dir/statistical_tests.json).",
    )
    args = parser.parse_args()

    results_dir = Path(args.results_dir)
    if not results_dir.exists():
        raise SystemExit(f"Results directory not found: {results_dir}")

    # Find all task results
    summary_files = list(results_dir.glob("*_summary.json"))
    if not summary_files:
        # Try to find JSONL files
        jsonl_files = list(results_dir.glob("*_paired.jsonl"))
        if not jsonl_files:
            raise SystemExit(f"No paired results found in {results_dir}")
        summary_files = jsonl_files

    all_stats: list[dict] = []

    for summary_path in sorted(summary_files):
        if summary_path.suffix == ".json":
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            task_id = summary.get("task_id", summary_path.stem.replace("_summary", ""))
        else:
            continue

        # Load detailed results
        detail_path = results_dir / f"{task_id}_paired.jsonl"
        if not detail_path.exists():
            print(f"WARNING: No detail file for {task_id}, skipping.")
            continue

        details = [
            json.loads(line)
            for line in detail_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

        if not details:
            continue

        base_correct = [d["base_correct"] for d in details]
        qlora_correct = [d["qlora_correct"] for d in details]
        base_metrics = [d["base_metric"] for d in details]
        qlora_metrics = [d["qlora_metric"] for d in details]

        task_type = summary.get("task_type", "mcq")
        metric_name = summary.get("metric", "accuracy")
        n = len(details)

        stats = compute_task_statistics(
            base_correct=base_correct,
            qlora_correct=qlora_correct,
            base_metrics=base_metrics,
            qlora_metrics=qlora_metrics,
            task_type=task_type,
            metric_name=metric_name,
            task_id=task_id,
            n=n,
            iterations=args.iterations,
            seed=args.seed,
        )

        all_stats.append(stats)

        # Print summary
        print(f"\n{'='*60}")
        print(f"Task: {task_id} (N={n}, type={task_type})")
        print(f"{'='*60}")
        print(f"  Base:   {stats['base_score']:.4f}")
        print(f"  QLoRA:  {stats['qlora_score']:.4f}")
        print(f"  Delta:  {stats['delta']:+.4f}")

        if "bootstrap" in stats:
            b = stats["bootstrap"]
            print(f"  95% CI for delta: [{b['delta']['ci_low']:+.4f}, {b['delta']['ci_high']:+.4f}]")
            print(f"  p-value (bootstrap): {b['p_value']:.4f}")

        if "mcnemar" in stats:
            m = stats["mcnemar"]
            print(f"  McNemar: chi2={m['chi2']:.4f}, p={m['p_value']:.4f} "
                  f"{'*' if m['significant_005'] else ''}{'*' if m['significant_001'] else ''}")
            print(f"    Base-only correct: {m['n_base_only_correct']}, "
                  f"QLoRA-only correct: {m['n_qlora_only_correct']}")

    # Save all stats
    output_path = Path(args.output) if args.output else results_dir / "statistical_tests.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(all_stats, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"\n\nStatistical tests saved to {output_path}")

    # Generate markdown table
    md_lines = [
        "# Paired Benchmark Statistical Tests",
        "",
        f"Bootstrap iterations: {args.iterations}, Seed: {args.seed}",
        "",
        "| Task | N | Base | QLoRA | Delta | 95% CI | p-value | Sig |",
        "|------|---|------|-------|-------|--------|---------|-----|",
    ]
    for s in all_stats:
        task = s["task_id"]
        n = s["n"]
        base = s["base_score"]
        qlora = s["qlora_score"]
        delta = s["delta"]
        ci = s.get("bootstrap", {}).get("delta", {})
        ci_lo = ci.get("ci_low", 0)
        ci_hi = ci.get("ci_high", 0)
        pval = s.get("bootstrap", {}).get("p_value", 1.0)
        sig = "***" if pval < 0.001 else ("**" if pval < 0.01 else ("*" if pval < 0.05 else ""))
        md_lines.append(
            f"| {task} | {n} | {base:.4f} | {qlora:.4f} | {delta:+.4f} | "
            f"[{ci_lo:+.4f}, {ci_hi:+.4f}] | {pval:.4f} | {sig} |"
        )

    md_path = results_dir / "statistical_tests.md"
    md_path.write_text("\n".join(md_lines), encoding="utf-8")
    print(f"Markdown table saved to {md_path}")


if __name__ == "__main__":
    main()
