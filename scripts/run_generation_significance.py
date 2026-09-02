from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.evaluation.significance import compare_generation, bootstrap_ci
from src.utils.io import save_json

GENERATION_METRICS = ["token_f1", "rouge_l", "citation_correctness", "citation_presence"]

# Pairs: (label, baseline_report, treatment_report)
DEFAULT_PAIRS = [
    ("qlora_vs_prompt_only",
     "reports/answer_generation_qwen_prompt_only_retrieved_report.json",
     "reports/answer_generation_qwen_qlora_retrieved_report.json"),
]


def render_markdown(results: list[dict]) -> str:
    lines = [
        "# Generation Significance Tests",
        "",
        "Paired bootstrap over per-question scores (Berg-Kirkpatrick et al., 2012). "
        "CIs are percentile bootstrap on the mean. Question-keyed, so pairing "
        "survives any malformed-record drops in either report.",
        "",
        "| comparison | metric | baseline mean [95% CI] | treatment mean [95% CI] | delta | p |",
        "|---|---|---|---|---|---:|---:|",
    ]
    for result in results:
        for row in result["comparisons"]:
            base = row["baseline"]
            treat = row["treatment"]
            lines.append(
                "| {cmp} | {m} | {bm} [{bl}, {bh}] | {tm} [{tl}, {th}] | {d:+.4f} | {p} |".format(
                    cmp=result.get("label", "generation"),
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
    parser = argparse.ArgumentParser(description="Paired bootstrap significance tests for generation metrics")
    parser.add_argument("--iterations", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--report-dir", default="reports")
    parser.add_argument("--baseline", default=None, help="Override first report path")
    parser.add_argument("--treatment", default=None, help="Override second report path")
    parser.add_argument("--metrics", nargs="+", default=GENERATION_METRICS)
    args = parser.parse_args()

    pairs = DEFAULT_PAIRS
    if args.baseline and args.treatment:
        pairs = [("custom", args.baseline, args.treatment)]

    results = []
    skipped = []
    for label, baseline, treatment in pairs:
        if not Path(baseline).exists() or not Path(treatment).exists():
            skipped.append(f"{label}: missing report")
            continue
        result = compare_generation(baseline, treatment, args.metrics, args.iterations, args.seed)
        result["label"] = label
        results.append(result)

    report_dir = Path(args.report_dir)
    payload = {"results": results, "skipped": skipped, "metrics": args.metrics}
    save_json(report_dir / "generation_significance.json", payload)
    (report_dir / "generation_significance.md").write_text(
        render_markdown(results), encoding="utf-8"
    )
    print(json.dumps({"comparisons_tested": len(results), "skipped": skipped}, indent=2))


if __name__ == "__main__":
    main()